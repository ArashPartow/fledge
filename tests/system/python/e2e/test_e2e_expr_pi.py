# -*- coding: utf-8 -*-

# FLEDGE_BEGIN
# See: http://fledge-iot.readthedocs.io/
# FLEDGE_END

""" Test end to end flow with:
        Expression south plugin
        Metadata filter plugin
        PI Server (C) plugin
"""


import http.client
import json
import time
import pytest
import utils
import math


__author__ = "Praveen Garg"
__copyright__ = "Copyright (c) 2019 Dianomic Systems"
__license__ = "Apache 2.0"
__version__ = "${VERSION}"


SOUTH_PLUGIN = "Expression"
SOUTH_PLUGIN_LANGUAGE = "C"

SVC_NAME = "Expr #1"
ASSET_NAME = "Expression"


class TestE2eExprPi:
    def get_ping_status(self, fledge_url):
        _connection = http.client.HTTPConnection(fledge_url)
        _connection.request("GET", '/fledge/ping')
        r = _connection.getresponse()
        assert 200 == r.status
        r = r.read().decode()
        jdoc = json.loads(r)
        return jdoc

    def get_statistics_map(self, fledge_url):
        _connection = http.client.HTTPConnection(fledge_url)
        _connection.request("GET", '/fledge/statistics')
        r = _connection.getresponse()
        assert 200 == r.status
        r = r.read().decode()
        jdoc = json.loads(r)
        return utils.serialize_stats_map(jdoc)


    @pytest.fixture
    def start_south_north(self, reset_and_start_fledge, add_south, enable_schedule, remove_directories,
                          south_branch, fledge_url, add_filter, filter_branch, filter_name,
                          start_north_pi_server_c_web_api, pi_host, pi_port,
                          clear_pi_system_through_pi_web_api, pi_admin, pi_passwd, pi_db):
        """ This fixture clone a south and north repo and starts both south and north instance

            reset_and_start_fledge: Fixture that resets and starts fledge, no explicit invocation, called at start
            add_south: Fixture that adds a south service with given configuration with enabled or disabled mode
            remove_directories: Fixture that remove directories created during the tests
        """

        # No need to give asset hierarchy in case of connector relay.
        dp_list = [ASSET_NAME, 'name', '']
        # There are three data points here. 1. ASSET_NAME  2. name as metadata filter is used.
        # 3. no data point (Asset name be used in this case.)
        asset_dict = {}
        asset_dict[ASSET_NAME] = dp_list
        # For connector relay we should not delete PI Point because
        # when the PI point is created again (after deletion) the compressing attribute for it
        # is always true. That means all the data is not stored in PI data archive.
        # We lose a large proportion of the data because of compressing attribute.
        # This is problematic for the fixture that verifies the data stored in PI.
        # clear_pi_system_through_pi_web_api(pi_host, pi_admin, pi_passwd, pi_db,
        #                                    [], asset_dict)

        cfg = {"expression": {"value": "tan(x)"}, "minimumX": {"value": "45"}, "maximumX": {"value": "45"},
               "stepX": {"value": "0"}}

        add_south(SOUTH_PLUGIN, south_branch, fledge_url, service_name=SVC_NAME, config=cfg,
                  plugin_lang=SOUTH_PLUGIN_LANGUAGE, start_service=True)

        filter_cfg = {"enable": "true"}
        filter_plugin = "metadata"
        add_filter(filter_plugin, filter_branch, filter_name, filter_cfg, fledge_url, SVC_NAME)

        # enable_schedule(fledge_url, SVC_NAME)

        start_north_pi_server_c_web_api(fledge_url, pi_host, pi_port, pi_db=pi_db, pi_user=pi_admin, pi_pwd=pi_passwd,
                                    taskname="NorthReadingsToPI")

        yield self.start_south_north

        remove_directories("/tmp/fledge-south-{}".format(SOUTH_PLUGIN.lower()))
        remove_directories("/tmp/fledge-filter-{}".format(filter_plugin))

    def test_end_to_end(self, start_south_north, disable_schedule, fledge_url, read_data_from_pi_asset_server, pi_host, pi_admin,
                        pi_passwd, pi_db, wait_time, retries, skip_verify_north_interface):
        """ Test that data is inserted in Fledge using expression south plugin & metadata filter, and sent to PI
            start_south_north: Fixture that starts Fledge with south service, add filter and north instance
            skip_verify_north_interface: Flag for assertion of data from Pi web API
            Assertions:
                on endpoint GET /fledge/asset
                on endpoint GET /fledge/asset/<asset_name> with applied data processing filter value
                data received from PI is same as data sent"""

        # Time to wait until north schedule runs
        time.sleep(wait_time * math.ceil(15/wait_time) + 15)

        ping_response = self.get_ping_status(fledge_url)
        assert 0 < ping_response["dataRead"]
        if not skip_verify_north_interface:
            assert 0 < ping_response["dataSent"]

        actual_stats_map = self.get_statistics_map(fledge_url)
        assert 0 < actual_stats_map[ASSET_NAME.upper()]
        assert 0 < actual_stats_map['READINGS']
        if not skip_verify_north_interface:
            assert 0 < actual_stats_map['Readings Sent']
            assert 0 < actual_stats_map['NorthReadingsToPI']

        conn = http.client.HTTPConnection(fledge_url)
        self._verify_ingest(conn)

        # disable schedule to stop the service and sending data
        disable_schedule(fledge_url, SVC_NAME)
        if not skip_verify_north_interface:
            self._verify_egress(read_data_from_pi_asset_server, pi_host, pi_admin, pi_passwd, pi_db, wait_time, retries)

        tracking_details = utils.get_asset_tracking_details(fledge_url, "Ingest")
        assert len(tracking_details["track"]), "Failed to track Ingest event"
        tracked_item = tracking_details["track"][0]
        assert SVC_NAME == tracked_item["service"]
        assert ASSET_NAME == tracked_item["asset"]
        assert "Expression" == tracked_item["plugin"]

        tracking_details = utils.get_asset_tracking_details(fledge_url, "Filter")
        assert len(tracking_details["track"]), "Failed to track Filter event"
        tracked_item = tracking_details["track"][0]
        assert SVC_NAME == tracked_item["service"]
        assert ASSET_NAME == tracked_item["asset"]
        assert "Meta #1" == tracked_item["plugin"]

        if not skip_verify_north_interface:
            egress_tracking_details = utils.get_asset_tracking_details(fledge_url,"Egress")
            assert len(egress_tracking_details["track"]), "Failed to track Egress event"
            tracked_item = egress_tracking_details["track"][0]
            assert "NorthReadingsToPI" == tracked_item["service"]
            assert ASSET_NAME == tracked_item["asset"]
            assert "OMF" == tracked_item["plugin"]

    def _verify_ingest(self, conn):

        conn.request("GET", '/fledge/asset')
        r = conn.getresponse()
        assert 200 == r.status
        r = r.read().decode()
        jdoc = json.loads(r)
        assert 1 == len(jdoc)
        assert ASSET_NAME == jdoc[0]["assetCode"]
        assert 0 < jdoc[0]["count"]

        conn.request("GET", '/fledge/asset/{}'.format(ASSET_NAME))
        r = conn.getresponse()
        assert 200 == r.status
        r = r.read().decode()
        jdoc = json.loads(r)
        assert 0 < len(jdoc)

        read = jdoc[0]["reading"]
        # FOGL-2438 values like tan(45) = 1.61977519054386 gets truncated to 1.6197751905 with ingest
        assert 1.6197751905 == read["Expression"]
        # verify filter is applied and we have {name: value} pair added by metadata filter
        assert "value" == read["name"]

    def _verify_egress(self, read_data_from_pi_asset_server, pi_host, pi_admin, pi_passwd, pi_db, wait_time, retries):
        retry_count = 0
        data_from_pi = None
        while (data_from_pi is None or data_from_pi == []) and retry_count < retries:
            data_from_pi = read_data_from_pi_asset_server(pi_host, pi_admin, pi_passwd, pi_db, ASSET_NAME, {"Expression", "name"})
            retry_count += 1
            time.sleep(wait_time * 2)

        if data_from_pi is None or retry_count == retries:
            assert False, "Failed to read data from PI"

        assert len(data_from_pi)
        assert "name" in data_from_pi
        assert "Expression" in data_from_pi
        assert isinstance(data_from_pi["name"], list)
        assert isinstance(data_from_pi["Expression"], list)
        # TODO: FOGL-2883: Test fails randomly in below assertion needs to be fixed
        # assert "value" in data_from_pi["name"]
        # FOGL-2438 values like tan(45) = 1.61977519054386 gets truncated to 1.6197751905 with ingest
        # assert 1.6197751905 in data_from_pi["Expression"]
