from azure.devops.connection import Connection
import logging
import sys


logger = logging.getLogger()
logger.setLevel(logging.INFO)

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
# formatter = logging.Formatter('%(asctime)s - %(funcName)20s() - %(levelname)s - %(message)s')


handler.setFormatter(formatter)

if logger.hasHandlers():
    logger.handlers.clear()

logger.addHandler(handler)


class OurADOObj(object):
    """Base Class for all our Azure Dev Ops API interactions under 'My Default Project Name' project
    """

    def __init__(self,  creds):
        self.org_url = 'https://mycompany.visualstudio.com'
        self.project_name_str = 'My Default Project Name'
        self.top_level_folder_path = '\\Automation'
        self.verbose_logging = False
        self.filtered_build_names_list = []

        # Connect to ADO
        self.connection = Connection(self.org_url, creds)
        # Get our project (TeamProjectReference object)
        self.ado_project = self.return_ado_project_by_name()

    def return_ado_project_by_name(self):
        """
        :return: TeamProjectReference object
        """
        # Get a client (the "core" client provides access to projects, teams, etc)
        core_client = self.connection.clients.get_core_client()
        # Get the first page of projects
        get_projects_response = core_client.get_projects()

        for project in get_projects_response.value:
            if project.name == self.project_name_str:
                logger.info('Successfully found %s project:' % self.project_name_str)
                if self.verbose_logging:
                    pretty_log_dict(project.__dict__)
                return project

        return False


class ADOTaskAgentObj(OurADOObj):
    """Sub Class for interacting with Task Agent objects in ADO 'My Default Project Name' project
    """

    def __init__(self,  creds, v51_client_version=False):
        OurADOObj.__init__(self, creds)
        self.agent_names_list = []
        self.project_name_str = 'My Default Project Name'
        self.agent_client = self.get_task_agent_client(use_v5_1_api=v51_client_version)

    def get_task_agent_client(self, use_v5_1_api=False):
        """
        :return: TaskAgentClient object

        https://docs.microsoft.com/en-us/rest/api/azure/devops/distributedtask/pools/get%20agent%20pools?view=azure-devops-rest-5.1
        https://docs.microsoft.com/en-us/rest/api/azure/devops/distributedtask/queues?view=azure-devops-rest-5.1

        See: \site-packages\azure\devops\released\task_agent\task_agent_client.py
        or
             \site-packages\azure\devops\v5_1\task_agent\task_agent_client.py

        To call this method the user's PAT token needs to have Agent rights set when the PAT is generated.
        """
        if use_v5_1_api:
            logger.info('Using v5.1 of ADO client API - this is not the released version')
            our_client = self.connection.clients_v5_1.get_task_agent_client()
        else:
            logger.info('Using release version of ADO client API')
            our_client = self.connection.clients.get_task_agent_client()

        return our_client

    def get_agent_pools(self):
        # return a list of TaskAgentPool objects
        pools = self.agent_client.get_agent_pools()
        return pools

    def get_single_agent_pool(self, pool_id):
        # return a single TaskAgentPool object
        # 119 is 'Quality Control Azure' agent pool
        our_pool = self.agent_client.get_agent_pool(pool_id)
        return our_pool

    def get_agents_in_pool(self, pool_id):
        # return a list of TaskAgent objects
        # 119 is Quality Control Azure
        pool_agents = self.agent_client.get_agents(pool_id, include_last_completed_request=True)
        return pool_agents

    def get_task_agent_queue(self, queue_id, project_name):
        # get_agent_queue only exists in v5.1 of the MS python Client API library
        # /site-packages/azure/devops/v5_1/task_agent/task_agent_client.py
        # So you need to have called get_task_agent_client with use_v5_1_api=True
        our_agent_queue = self.agent_client.get_agent_queue(1516, project=self.project_name_str)

        return our_agent_queue


class ADOBuildObj(OurADOObj):
    """Sub Class for interacting with Build objects in ADO 'My Default Project Name' project
    """

    def __init__(self,  creds, v6_api=False):
        OurADOObj.__init__(self, creds)
        self.filtered_build_names_list = []
        self.using_v6_build_client = v6_api
        self.build_def_refs_list_under_project = self.get_list_of_build_definition_references_under_project(v6_api)

    def get_list_of_build_definition_references_under_project(self, use_v6_api=False):
        """
        :return: list of BuildDefinitionReference objects
        """
        logger.info('Getting definitions under project: %s' % self.ado_project.name)

        if use_v6_api:
            build_client = self.connection.clients_v6_0.get_build_client()
            logger.info('Using v6.0 ADO build client')
        else:
            build_client = self.connection.clients.get_build_client()
            logger.info('Using release version of ADO build client')

        definitions = build_client.get_definitions(self.ado_project.id)

        if self.using_v6_build_client:
            return definitions
        else:
            return definitions.value

    def return_build_names_list_for_builds_under_path(self, find_under_path):
        """
        return: list of strings - definition names of all the builds under specified path
        """
        list_of_build_names = []

        logger.info('filtering list for builds under path %s' % find_under_path)
        for definition in self.build_def_refs_list_under_project:
            if find_under_path in definition.path:
                # only get definitions that have valid ids and names
                if definition.id and definition.name:
                    list_of_build_names.append(definition.name)

        if self.verbose_logging:
            pretty_log_list(list_of_build_names)

        return list_of_build_names

    def filter_builds_list(self, build_names_under_automation, must_include_string, verbose=False):
        filtered_list_of_build_ids = []
        for definition in self.build_def_refs_list_under_project:

            for this_build_under_automation in build_names_under_automation:
                # if this build name is in the list under our project and contains our filter string then add to list
                if this_build_under_automation in definition.name \
                        and must_include_string.lower() in this_build_under_automation.lower():
                    # if it does not have a name and id then it is not a build (probably a folder); we don't want it
                    if definition.id and definition.name:
                        filtered_list_of_build_ids.append(definition.name)

        if verbose:
            pretty_log_list(filtered_list_of_build_ids)

        return filtered_list_of_build_ids

    def get_build_by_name_return_definition_reference(self, pipeline_name):
        # Note: returns a BuildDefinitionReference not a BuildDefinition
        # get the ID and then use get_single_build_definition_by_id to get definition
        for definition in self.build_def_refs_list_under_project:
            if definition.name == pipeline_name:
                return definition

        return False

    def return_target_build_definition_references_dict(self):
        """
        Return a dictionary of BuildDefinitionReference objects for each filtered pipeline
        Dict like Key: Build names, value: BuildDefinitionReference object
        """
        target_build_def_refs_dict = {}
        for each_build in self.filtered_build_names_list:
            this_defintion = self.get_build_by_name_return_definition_reference(each_build)
            target_build_def_refs_dict[this_defintion.name] = this_defintion

        return target_build_def_refs_dict

    def return_key_build_definition_attributes_dict(self, log=True):
        """
        :param log: whether to log to console
        :return: a results dictionary of the form index: {dict of attributes we care about}
        """
        results_dict = {}
        for index, each_build in enumerate(self.filtered_build_names_list):
            this_defintion = self.get_build_by_name_return_definition_reference(each_build)

            single_result = {'id': this_defintion.id,
                             'name': this_defintion.name,
                             'queue_status': this_defintion.queue_status}

            results_dict[index] = single_result

            if log:
                # log key details to console
                logger.info("BuildDefinitionReference, ID:" + str(this_defintion.id) + ", Name: "
                            + this_defintion.name + ", Queue_status:" + this_defintion.queue_status)
                # ", Pool: " + definition.queue.name - not useful as we set Agent Pool in YAML.

        return results_dict

    def return_filtered_not_sf_testrunner_build_definitions_list(self, envt, filter_under_path='\\Automation\\'):
        """
        Get a list of build names from under the 'Automation' folder in ADO 'My Default Project Name' project,
        then filter it:
          - so that it only includes pipelines under the filter_under_path folder

        :param envt: string - environment name (e.g. 'tsaexit','bat')
        :param filter_under_path : folder in ADO under which to look
        :return: list of build names (strings) under our project filtereed by our criteria
        """

        logger.info('-- Getting %s testrunner pipeline details under %s' % (envt, filter_under_path))
        self.filtered_build_names_list = self.return_build_names_list_for_builds_under_path(filter_under_path)
        logger.info('---- There are %s pipelines found under %s folder path'
                    % (len(self.filtered_build_names_list), filter_under_path))

        return self.filtered_build_names_list

    def return_filtered_testrunner_build_definitions_list(self, envt, filter_under_path='\\Automation\\MyDelivery'):
        """
        Get a list of MyDelivery build names from under the 'Automation' folder in ADO 'My Default Project Name' project,
        then filter it:
          - so that it only includes Saleforce Testrunner pipelines
          - by test environment (string) in the pipeline name (e.g.uatcopy1, staging) where one is given

        :param envt: string - environment name (e.g. 'any','staging', 'uatcopy1'')
        :param filter_under_path : folder in ADO under which to look
        :return: list of build names (strings) under our project filtereed by our criteria
        """

        logger.info('-- Getting SF testrunner pipeline details')
        self.filtered_build_names_list = self.return_build_names_list_for_builds_under_path(filter_under_path)
        logger.info('---- There are %s pipelines found under %s folder path'
                    % (len(self.filtered_build_names_list), filter_under_path))

        # filter by SF prefix
        logger.info('-- Filtering SF testrunner pipeline details based on SF_ prefix included in name')
        self.filtered_build_names_list = self.filter_builds_list(self.filtered_build_names_list, 'SF_',
                                                                 verbose=False)
        logger.info('---- Filtered by SF_, count now:- %s pipelines ' % len(self.filtered_build_names_list))

        logger.info('-- Filtering SF testrunner pipeline details based on CloudTests included in name')
        self.filtered_build_names_list = self.filter_builds_list(self.filtered_build_names_list, 'CloudTests',
                                                                 verbose=False)
        logger.info('---- Filtered by CloudTests, count now:- %s pipelines ' % len(self.filtered_build_names_list))

        # filter by envt
        if envt not in ('any', 'sf_all'):
            logger.info('-- Filtering SF testrunner pipeline details based on envt: %s' % envt)
            self.filtered_build_names_list =\
                self.filter_builds_list(self.filtered_build_names_list, '_' + envt + '_', verbose=False)
            logger.info('---- Filtered by envt %s, count now:- %s pipelines ' %
                        ('_' + envt + '_', len(self.filtered_build_names_list)))

        return self.filtered_build_names_list

    def get_single_build_definition_by_id(self, our_definition_id):
        """
        :param our_definition_id:
        :return: a single BuildDefinition object
        """
        project = self.ado_project
        if self.verbose_logging:
            logger.info('Getting single definition: %s, under project: %s' % (our_definition_id, project.name))

        build_client = self.connection.clients.get_build_client()
        definition = build_client.get_definition(project.id, our_definition_id, include_latest_builds=True)

        return definition

    def set_single_build_definition_queue_status(self, defintion_id, set_to_status, build_def=False):

        build_client = self.connection.clients.get_build_client()

        # get build definition we want to manipulate if we don't have it already
        if build_def:
            # we have passed in the BuildDefinition Object
            single_def = build_def
        else:
            # get the BuildDefinition object we want by ID
            single_def = self.get_single_build_definition_by_id(defintion_id)

        logger.info('Before any updates, the BuildDefinition id: %s has queue_status: %s'
                    % (single_def.id, single_def.queue_status))

        if set_to_status in ('disabled', 'enabled', 'paused'):
            single_def.queue_status = set_to_status
        else:
            raise BaseException('You must choose disabled, enabled or paused for the queue_status you want to set.')

        # update that defn for the param we need to set
        logger.info(
            'About to update BuildDefinition id: %s to queue_status: %s' % (single_def.id, single_def.queue_status))

        # do the update defn call
        build_client.update_definition(single_def, 'My Default Project Name', single_def.id)
        logger.info('The build with id %s (%s) has been updated succesfully to have queue status: %s'
                    % (single_def.id, single_def.name, single_def.queue_status))

    def get_latest_build_report_by_build_id(self, build_definition_id):
        """
        Get a build 'report' as per
        # https://docs.microsoft.com/en-us/rest/api/azure/devops/build/report/get?view=azure-devops-rest-6.0
        For the last_completed_build of the build id

        This is useful as it includes the test results (report.content)

        :param build_definition_id: a valid ADO BuildDefinition's id
        :return: ADO BuildReportMetadata object
        """

        project = self.ado_project
        if self.verbose_logging:
            logger.info('Getting single definition: %s, under project: %s' % (build_definition_id, project.name))

        # NOTE: reports requires clients_v6.0
        build_client = self.connection.clients_v6_0.get_build_client()
        definition = build_client.get_definition(project.id, build_definition_id, include_latest_builds=True)

        last_completed_build = definition.latest_completed_build

        # https://docs.microsoft.com/en-us/rest/api/azure/devops/build/report/get?view=azure-devops-rest-6.0
        # /site-packages/azure/devops/v6_0/build/build_client.py
        report = build_client.get_build_report(project.id, last_completed_build.id)

        # not sure the below is useful - TODO: explore this
        #report_html = build_client.get_build_report_html_content(project.id, last_completed_build.id)

        return report


class ADOTestResultsObj(OurADOObj):
    """Sub Class for interacting with Test Results objects in ADO 'My Default Project Name' project
    """

    def __init__(self,  creds, v6_api=False):
        OurADOObj.__init__(self, creds)
        self.filtered_build_names_list = []
        self.using_v6_build_client = v6_api
        # self.build_def_refs_list_under_project = self.get_list_of_build_definition_references_under_project(v6_api)

    def get_test_result_log(self, run_id, use_v6_api=False):
        """
        :return: list of GetTestResultLogs objects
        """
        logger.info('Getting results under project: %s' % self.ado_project.name)

        if use_v6_api:
            test_result_client = self.connection.clients_v6_0.get_test_results_client()
            logger.info('Using v6.0 ADO results client')
        else:
            test_result_client = self.connection.clients.get_test_results_client()
            logger.info('Using release version of ADO results client')

        #our_result = test_result_client.get_test_result_logs(self.ado_project.id, run_id)

        run_id = 1603112
        result_id = 100066
        attach_type = 'generalAttachment'

        #def get_test_result_logs(self, project, run_id, result_id, type, directory_path=None, file_name_prefix=None, fetch_meta_data=None, top=None, continuation_token=None):
        our_result = test_result_client.get_test_result_logs(self.ado_project.id, run_id, result_id, attach_type)

        return our_result


class ADOTestClientObj(OurADOObj):
    """Sub Class for interacting with Test Results objects in ADO 'My Default Project Name' project
    """

    def __init__(self,  creds, v6_api=False):
        OurADOObj.__init__(self, creds)
        self.filtered_build_names_list = []
        self.using_v6_build_client = v6_api
        # self.build_def_refs_list_under_project = self.get_list_of_build_definition_references_under_project(v6_api)

    def get_test_runs(self, our_build_uri, use_v6_api=False):
        """
        Get Test runs using the build URI
        Useful to find out run ids for a specific build

        :param our_build_uri: last completed build uri
        :param use_v6_api:
        :return:
        """
        logger.info('Getting test runs stats under project: %s using build_uri filter: %s'
                    % (self.ado_project.name, our_build_uri))

        if use_v6_api:
            test_result_client = self.connection.clients_v6_0.get_test_client()
            logger.info('Using v6.0 ADO test client')
        else:
            test_result_client = self.connection.clients.get_test_client()
            logger.info('Using release version of ADO test client')

        # https://docs.microsoft.com/en-us/rest/api/azure/devops/test/runs/list?view=azure-devops-rest-5.0
        # get_test_runs(self, project, build_uri=None, owner=None, tmi_run_id=None, plan_id=None,
        # include_run_details=None, automated=None, skip=None, top=None)
        auto_test_runs =\
            test_result_client.get_test_runs(self.ado_project.id, build_uri=our_build_uri, include_run_details=True)

        #auto_test_runs = test_result_client.get_test_runs(self.ado_project.id, automated=True, include_run_details=True)
        # our_result = test_result_client.query_test_runs(self.ado_project.id, None, None, build_def_ids='527') # build_ids='135297')
        # build_ids=None, build_def_ids=None,

        return auto_test_runs

    def get_test_run_statistics(self, run_id, use_v6_api=False):
        """
        https://docs.microsoft.com/en-us/rest/api/azure/devops/test/runs/get%20test%20run%20statistics?view=azure-devops-rest-5.0

        :return: GetTestRunStatistics object
        """
        logger.info('Getting run stats under project: %s for run_id: %s' % (self.ado_project.name, run_id) )

        if use_v6_api:
            test_result_client = self.connection.clients_v6_0.get_test_client()
            logger.info('Using v6.0 ADO test client')
        else:
            test_result_client = self.connection.clients.get_test_client()
            logger.info('Using release version of ADO test client')

        our_result = test_result_client.get_test_run_statistics(self.ado_project.id, run_id)

        return our_result


def pretty_log_dict(our_dict):
    for k, v in our_dict.items():
        logger.info("%s: %s" % (k, v))


def pretty_log_list(our_list):
    for this in our_list:
        logger.info(this)
