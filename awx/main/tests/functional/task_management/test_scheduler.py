import pytest
import mock
from datetime import timedelta, datetime

from django.core.cache import cache

from awx.main.scheduler import TaskManager


@pytest.mark.django_db
def test_single_job_scheduler_launch(default_instance_group, job_template_factory, mocker):
    objects = job_template_factory('jt', organization='org1', project='proj',
                                   inventory='inv', credential='cred',
                                   jobs=["job_should_start"])
    j = objects.jobs["job_should_start"]
    j.status = 'pending'
    j.save()
    with mocker.patch("awx.main.scheduler.TaskManager.start_task"):
        TaskManager().schedule()
        TaskManager.start_task.assert_called_once_with(j, default_instance_group, [])


@pytest.mark.django_db
def test_single_jt_multi_job_launch_blocks_last(default_instance_group, job_template_factory, mocker):
    objects = job_template_factory('jt', organization='org1', project='proj',
                                   inventory='inv', credential='cred',
                                   jobs=["job_should_start", "job_should_not_start"])
    j1 = objects.jobs["job_should_start"]
    j1.status = 'pending'
    j1.save()
    j2 = objects.jobs["job_should_not_start"]
    j2.status = 'pending'
    j2.save()
    with mock.patch("awx.main.scheduler.TaskManager.start_task"):
        TaskManager().schedule()
        TaskManager.start_task.assert_called_once_with(j1, default_instance_group, [])
        j1.status = "successful"
        j1.save()
    with mocker.patch("awx.main.scheduler.TaskManager.start_task"):
        TaskManager().schedule()
        TaskManager.start_task.assert_called_once_with(j2, default_instance_group, [])


@pytest.mark.django_db
def test_single_jt_multi_job_launch_allow_simul_allowed(default_instance_group, job_template_factory, mocker):
    objects = job_template_factory('jt', organization='org1', project='proj',
                                   inventory='inv', credential='cred',
                                   jobs=["job_should_start", "job_should_not_start"])
    jt = objects.job_template
    jt.save()

    j1 = objects.jobs["job_should_start"]
    j1.allow_simultaneous = True
    j1.status = 'pending'
    j1.save()
    j2 = objects.jobs["job_should_not_start"]
    j2.allow_simultaneous = True
    j2.status = 'pending'
    j2.save()
    with mock.patch("awx.main.scheduler.TaskManager.start_task"):
        TaskManager().schedule()
        TaskManager.start_task.assert_has_calls([mock.call(j1, default_instance_group, []),
                                                 mock.call(j2, default_instance_group, [])])


@pytest.mark.django_db
def test_multi_jt_capacity_blocking(default_instance_group, job_template_factory, mocker):
    objects1 = job_template_factory('jt1', organization='org1', project='proj1',
                                    inventory='inv1', credential='cred1',
                                    jobs=["job_should_start"])
    objects2 = job_template_factory('jt2', organization='org2', project='proj2',
                                    inventory='inv2', credential='cred2',
                                    jobs=["job_should_not_start"])
    j1 = objects1.jobs["job_should_start"]
    j1.status = 'pending'
    j1.save()
    j2 = objects2.jobs["job_should_not_start"]
    j2.status = 'pending'
    j2.save()
    tm = TaskManager()
    with mock.patch('awx.main.models.Job.task_impact', new_callable=mock.PropertyMock) as mock_task_impact:
        mock_task_impact.return_value = 500
        with mock.patch.object(TaskManager, "start_task", wraps=tm.start_task) as mock_job:
            tm.schedule()
            mock_job.assert_called_once_with(j1, default_instance_group, [])
            j1.status = "successful"
            j1.save()
    with mock.patch.object(TaskManager, "start_task", wraps=tm.start_task) as mock_job:
        tm.schedule()
        mock_job.assert_called_once_with(j2, default_instance_group, [])
    
    

@pytest.mark.django_db
def test_single_job_dependencies_project_launch(default_instance_group, job_template_factory, mocker):
    objects = job_template_factory('jt', organization='org1', project='proj',
                                   inventory='inv', credential='cred',
                                   jobs=["job_should_start"])
    j = objects.jobs["job_should_start"]
    j.status = 'pending'
    j.save()
    p = objects.project
    p.scm_update_on_launch = True
    p.scm_update_cache_timeout = 0
    p.scm_type = "git"
    p.scm_url = "http://github.com/ansible/ansible.git"
    p.save()
    with mock.patch("awx.main.scheduler.TaskManager.start_task"):
        tm = TaskManager()
        with mock.patch.object(TaskManager, "create_project_update", wraps=tm.create_project_update) as mock_pu:
            tm.schedule()
            mock_pu.assert_called_once_with(j)
            pu = [x for x in p.project_updates.all()]
            assert len(pu) == 1
            TaskManager.start_task.assert_called_once_with(pu[0], default_instance_group, [j])
            pu[0].status = "successful"
            pu[0].save()
    with mock.patch("awx.main.scheduler.TaskManager.start_task"):
        TaskManager().schedule()
        TaskManager.start_task.assert_called_once_with(j, default_instance_group, [])


@pytest.mark.django_db
def test_single_job_dependencies_inventory_update_launch(default_instance_group, job_template_factory, mocker, inventory_source_factory):
    objects = job_template_factory('jt', organization='org1', project='proj',
                                   inventory='inv', credential='cred',
                                   jobs=["job_should_start"])
    j = objects.jobs["job_should_start"]
    j.status = 'pending'
    j.save()
    i = objects.inventory
    ii = inventory_source_factory("ec2")
    ii.source = "ec2"
    ii.update_on_launch = True
    ii.update_cache_timeout = 0
    ii.save()
    i.inventory_sources.add(ii)
    with mock.patch("awx.main.scheduler.TaskManager.start_task"):
        tm = TaskManager()
        with mock.patch.object(TaskManager, "create_inventory_update", wraps=tm.create_inventory_update) as mock_iu:
            tm.schedule()
            mock_iu.assert_called_once_with(j, ii)
            iu = [x for x in ii.inventory_updates.all()]
            assert len(iu) == 1
            TaskManager.start_task.assert_called_once_with(iu[0], default_instance_group, [j])
            iu[0].status = "successful"
            iu[0].save()
    with mock.patch("awx.main.scheduler.TaskManager.start_task"):
        TaskManager().schedule()
        TaskManager.start_task.assert_called_once_with(j, default_instance_group, [])
        

@pytest.mark.django_db
def test_shared_dependencies_launch(default_instance_group, job_template_factory, mocker, inventory_source_factory):
    objects = job_template_factory('jt', organization='org1', project='proj',
                                   inventory='inv', credential='cred',
                                   jobs=["first_job", "second_job"])
    j1 = objects.jobs["first_job"]
    j1.status = 'pending'
    j1.save()
    j2 = objects.jobs["second_job"]
    j2.status = 'pending'
    j2.save()
    p = objects.project
    p.scm_update_on_launch = True
    p.scm_update_cache_timeout = 300
    p.scm_type = "git"
    p.scm_url = "http://github.com/ansible/ansible.git"
    p.save()

    i = objects.inventory
    ii = inventory_source_factory("ec2")
    ii.source = "ec2"
    ii.update_on_launch = True
    ii.update_cache_timeout = 300
    ii.save()
    i.inventory_sources.add(ii)

    with mock.patch("awx.main.scheduler.TaskManager.start_task"):
        TaskManager().schedule()
        pu = p.project_updates.first()
        iu = ii.inventory_updates.first()
        TaskManager.start_task.assert_has_calls([mock.call(pu, default_instance_group, [iu, j1]),
                                                 mock.call(iu, default_instance_group, [pu, j1])])
        pu.status = "successful"
        pu.finished = pu.created + timedelta(seconds=1)
        pu.save()
        iu.status = "successful"
        iu.finished = iu.created + timedelta(seconds=1)
        iu.save()
    with mock.patch("awx.main.scheduler.TaskManager.start_task"):
        TaskManager().schedule()
        TaskManager.start_task.assert_called_once_with(j1, default_instance_group, [])
        j1.status = "successful"
        j1.save()
    with mock.patch("awx.main.scheduler.TaskManager.start_task"):
        TaskManager().schedule()
        TaskManager.start_task.assert_called_once_with(j2, default_instance_group, [])
    pu = [x for x in p.project_updates.all()]
    iu = [x for x in ii.inventory_updates.all()]
    assert len(pu) == 1
    assert len(iu) == 1


@pytest.mark.django_db
def test_cleanup_interval():
    assert cache.get('last_celery_task_cleanup') is None

    TaskManager().cleanup_inconsistent_celery_tasks()
    last_cleanup = cache.get('last_celery_task_cleanup')
    assert isinstance(last_cleanup, datetime)

    TaskManager().cleanup_inconsistent_celery_tasks()
    assert cache.get('last_celery_task_cleanup') == last_cleanup


@pytest.mark.django_db
@mock.patch('awx.main.tasks._send_notification_templates')
@mock.patch.object(TaskManager, 'get_active_tasks', lambda self: [[], []])
@mock.patch.object(TaskManager, 'get_running_tasks')
def test_cleanup_inconsistent_task(get_running_tasks, notify):
    orphaned_task = mock.Mock(job_explanation='')
    get_running_tasks.return_value = [orphaned_task]
    TaskManager().cleanup_inconsistent_celery_tasks()

    notify.assert_called_once_with(orphaned_task, 'failed')
    orphaned_task.websocket_emit_status.assert_called_once_with('failed')
    assert orphaned_task.status == 'failed'
    assert orphaned_task.job_explanation == (
        'Task was marked as running in Tower but was not present in Celery, so it has been marked as failed.'
    )
