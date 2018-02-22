# -*- coding: utf-8 -*-

# FOGLAMP_BEGIN
# See: http://foglamp.readthedocs.io/
# FOGLAMP_END


import json
from unittest.mock import MagicMock, patch
from aiohttp import web
import pytest
from datetime import timedelta
import uuid
from foglamp.services.core import routes
from foglamp.services.core import connect
from foglamp.common.storage_client.storage_client import StorageClient
from foglamp.services.core import server
from foglamp.services.core.scheduler.scheduler import Scheduler
from foglamp.services.core.scheduler.entities import ScheduledProcess, Schedule, Task, IntervalSchedule, TimedSchedule, StartUpSchedule, ManualSchedule
from foglamp.services.core.scheduler.exceptions import *

__author__ = "Vaibhav Singhal"
__copyright__ = "Copyright (c) 2017 OSIsoft, LLC"
__license__ = "Apache 2.0"
__version__ = "${VERSION}"


@pytest.allure.feature("unit")
@pytest.allure.story("api", "core")
class TestScheduledProcesses:

    @pytest.fixture
    def client(self, loop, test_client):
        app = web.Application(loop=loop)
        # fill the routes table
        routes.setup(app)
        return loop.run_until_complete(test_client(app))

    async def test_get_scheduled_processes(self, client):

        async def mock_coro():
            processes = []
            process = ScheduledProcess()
            process.name = "foo"
            process.script = "bar"
            processes.append(process)
            return processes

        server.Server.scheduler = Scheduler(None, None)
        with patch.object(server.Server.scheduler, 'get_scheduled_processes', return_value=mock_coro()):
            resp = await client.get('/foglamp/schedule/process')
            result = await resp.text()
            json_response = json.loads(result)
        assert {'processes': ['foo']} == json_response

    async def test_get_scheduled_process(self, client):
        storage_client_mock = MagicMock(StorageClient)
        payload = '{"return": ["name"], "where": {"column": "name", "condition": "=", "value": "purge"}}'
        response = {'rows': [{'name': 'purge'}], 'count': 1}
        with patch.object(connect, 'get_storage', return_value=storage_client_mock):
                with patch.object(storage_client_mock, 'query_tbl_with_payload',
                                  return_value=response) as mock_storage_call:
                    resp = await client.get('/foglamp/schedule/process/purge')
                    assert 200 == resp.status
                    result = await resp.text()
                    json_response = json.loads(result)
                    assert 'purge' == json_response
                mock_storage_call.assert_called_with('scheduled_processes', payload)

    async def test_get_scheduled_process_bad_data(self, client):
        storage_client_mock = MagicMock(StorageClient)
        response = {'rows': [], 'count': 0}
        with patch.object(connect, 'get_storage', return_value=storage_client_mock):
                with patch.object(storage_client_mock, 'query_tbl_with_payload',
                                  return_value=response):
                    resp = await client.get('/foglamp/schedule/process/bla')
                    assert 404 == resp.status
                    assert 'No such Scheduled Process: bla.' == resp.reason


class TestSchedules:
    _random_uuid = uuid.uuid4()

    @pytest.fixture
    def client(self, loop, test_client):
        app = web.Application(loop=loop)
        # fill the routes table
        routes.setup(app)
        return loop.run_until_complete(test_client(app))

    async def test_get_schedules(self, client):
        async def mock_coro():
            schedules = []
            schedule = StartUpSchedule()
            schedule.schedule_id = "1"
            schedule.exclusive = True
            schedule.enabled = True
            schedule.name = "foo"
            schedule.process_name = "bar"
            schedule.repeat = timedelta(seconds=30)
            schedule.time = None
            schedule.day = None
            schedules.append(schedule)
            return schedules

        server.Server.scheduler = Scheduler(None, None)
        with patch.object(server.Server.scheduler, 'get_schedules', return_value=mock_coro()):
            resp = await client.get('/foglamp/schedule')
            assert 200 == resp.status
            result = await resp.text()
            json_response = json.loads(result)
            assert {'schedules': [
                {'name': 'foo', 'day': None, 'type': 'STARTUP', 'processName': 'bar',
                 'time': 0, 'id': '1', 'exclusive': True, 'enabled': True, 'repeat': 30.0}
            ]} == json_response

    async def test_get_schedule(self, client):
        async def mock_coro():
            schedule = StartUpSchedule()
            schedule.schedule_id = self._random_uuid
            schedule.exclusive = True
            schedule.enabled = True
            schedule.name = "foo"
            schedule.process_name = "bar"
            schedule.repeat = timedelta(seconds=30)
            schedule.time = None
            schedule.day = None
            return schedule

        server.Server.scheduler = Scheduler(None, None)
        with patch.object(server.Server.scheduler, 'get_schedule', return_value=mock_coro()):
            resp = await client.get('/foglamp/schedule/{}'.format(self._random_uuid))
            assert 200 == resp.status
            result = await resp.text()
            json_response = json.loads(result)
            assert {'id': str(self._random_uuid),
                    'name': 'foo', 'repeat': 30.0, 'enabled': True,
                    'processName': 'bar', 'type': 'STARTUP', 'day': None,
                    'time': 0, 'exclusive': True} == json_response

    async def test_get_schedule_bad_data(self, client):
            resp = await client.get('/foglamp/schedule/{}'.format("bla"))
            assert 404 == resp.status
            assert 'Invalid Schedule ID bla' == resp.reason

    @pytest.mark.parametrize("excep, response_code, response_message", [
        (ScheduleNotFoundError(_random_uuid), 404, 'Schedule not found: {}'.format(_random_uuid)),
        (ValueError, 404, None),
    ])
    async def test_get_schedule_exceptions(self, client, excep, response_code, response_message):
        server.Server.scheduler = Scheduler(None, None)
        with patch.object(server.Server.scheduler, 'get_schedule', side_effect=excep):
            resp = await client.get('/foglamp/schedule/{}'.format(self._random_uuid))
            assert response_code == resp.status
            assert response_message == resp.reason

    async def test_enable_schedule(self, client):
        async def mock_coro():
            return True, "Schedule successfully enabled"
        server.Server.scheduler = Scheduler(None, None)
        with patch.object(server.Server.scheduler, 'enable_schedule', return_value=mock_coro()):
            resp = await client.put('/foglamp/schedule/{}/enable'.format(self._random_uuid))
            assert 200 == resp.status
            result = await resp.text()
            json_response = json.loads(result)
            assert {'status': True, 'message': 'Schedule successfully enabled',
                    'scheduleId': '{}'.format(self._random_uuid)} == json_response

    async def test_enable_schedule_bad_data(self, client):
            resp = await client.put('/foglamp/schedule/{}/enable'.format("bla"))
            assert 404 == resp.status
            assert 'Invalid Schedule ID bla' == resp.reason

    @pytest.mark.parametrize("excep, response_code, response_message", [
        (ScheduleNotFoundError(_random_uuid), 404, 'Schedule not found: {}'.format(_random_uuid)),
        (ValueError, 404, None),
    ])
    async def test_enable_schedule_exceptions(self, client, excep, response_code, response_message):
        server.Server.scheduler = Scheduler(None, None)
        with patch.object(server.Server.scheduler, 'enable_schedule', side_effect=excep):
            resp = await client.put('/foglamp/schedule/{}/enable'.format(self._random_uuid))
            assert response_code == resp.status
            assert response_message == resp.reason

    async def test_disable_schedule(self, client):
        async def mock_coro():
            return True, "Schedule successfully disabled"
        server.Server.scheduler = Scheduler(None, None)
        with patch.object(server.Server.scheduler, 'disable_schedule', return_value=mock_coro()):
            resp = await client.put('/foglamp/schedule/{}/disable'.format(self._random_uuid))
            assert 200 == resp.status
            result = await resp.text()
            json_response = json.loads(result)
            assert {'status': True, 'message': 'Schedule successfully disabled',
                    'scheduleId': '{}'.format(self._random_uuid)} == json_response

    async def test_disable_schedule_bad_data(self, client):
            resp = await client.put('/foglamp/schedule/{}/disable'.format("bla"))
            assert 404 == resp.status
            assert 'Invalid Schedule ID bla' == resp.reason

    @pytest.mark.parametrize("excep, response_code, response_message", [
        (ScheduleNotFoundError(_random_uuid), 404, 'Schedule not found: {}'.format(_random_uuid)),
        (ValueError, 404, None),
    ])
    async def test_disable_schedule_exceptions(self, client, excep, response_code, response_message):
        server.Server.scheduler = Scheduler(None, None)
        with patch.object(server.Server.scheduler, 'disable_schedule', side_effect=excep):
            resp = await client.put('/foglamp/schedule/{}/disable'.format(self._random_uuid))
            assert response_code == resp.status
            assert response_message == resp.reason

    async def test_start_schedule(self, client):
        async def mock_coro():
            return ""

        server.Server.scheduler = Scheduler(None, None)
        with patch.object(server.Server.scheduler, 'get_schedule', return_value=mock_coro()) as mock_get_schedule:
            with patch.object(server.Server.scheduler, 'queue_task', return_value=mock_coro()) as mock_queue_task:
                resp = await client.post('/foglamp/schedule/start/{}'.format(self._random_uuid))
                assert 200 == resp.status
                result = await resp.text()
                json_response = json.loads(result)
                assert {'message': 'Schedule started successfully',
                        'id': '{}'.format(self._random_uuid)} == json_response
                mock_queue_task.assert_called_once_with(uuid.UUID('{}'.format(self._random_uuid)))
            mock_get_schedule.assert_called_once_with(uuid.UUID('{}'.format(self._random_uuid)))

    async def test_start_schedule_bad_data(self, client):
            resp = await client.post('/foglamp/schedule/start/{}'.format("bla"))
            assert 404 == resp.status
            assert 'Invalid Schedule ID bla' == resp.reason

    @pytest.mark.parametrize("excep, response_code, response_message", [
        (ScheduleNotFoundError(_random_uuid), 404, 'Schedule not found: {}'.format(_random_uuid)),
        (NotReadyError(), 404, None),
        (ValueError, 404, None),
    ])
    async def test_start_schedule_exceptions(self, client, excep, response_code, response_message):
        server.Server.scheduler = Scheduler(None, None)
        with patch.object(server.Server.scheduler, 'get_schedule', side_effect=excep):
            resp = await client.post('/foglamp/schedule/start/{}'.format(self._random_uuid))
            assert response_code == resp.status
            assert response_message == resp.reason
