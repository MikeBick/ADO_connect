import argparse
import logging
import sys
from types import SimpleNamespace
from msrest.authentication import BasicAuthentication

import general_utils
from ado_utils import ADOBuildObj, ADOTestClientObj, ADOTestResultsObj

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


def main():
    """
    Get specific test run data from ADO for the last completed build associated with testrunner build pipelines,
     by specified environment.

    :return: 1 or 0
    """
    logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser(description='Get specific test run data from ADO for the last completed build'
                                                 ' associated with testrunner build pipelines,'
                                                 ' by specified environment.')
    parser.add_argument('--pat', '-p', required=True, default=False,
                        help="PAT token generated within ADO for user running script")
    parser.add_argument('--envt', '-e', choices=('sf_all', 'uatcopy1', 'staging', 'projone', 'projtwo'),
                        required=True)

    args = parser.parse_args()

    personal_access_token = args.pat
    logger.info('A PAT variable has been passed in as expected.')

    # instantiate instance of our ADO object, which connects to ADO, gets our project & build definitions under project
    our_client = ADOBuildObj(creds=BasicAuthentication('PAT', personal_access_token), v6_api=True)

    # a results object for us to store results we get back from ADO and want to keep
    our_results = SimpleNamespace()

    # get filtered_build_names_list (a list of pipeline names as strings)
    if args.envt == 'projone':
        our_results.filtered_build_names_list =\
            our_client.return_filtered_not_sf_testrunner_build_definitions_list(
                args.envt, filter_under_path='\\Automation\\projone\\Active_Testrunners')
    elif args.envt == 'projtwo':
        our_results.filtered_build_names_list =\
            our_client.return_filtered_not_sf_testrunner_build_definitions_list(
                args.envt, filter_under_path='\\Automation\\projtwo\\Active_Testrunners')
    else:
        our_results.filtered_build_names_list =\
            our_client.return_filtered_testrunner_build_definitions_list(args.envt,
                                                                         filter_under_path='\\Automation\\MyDelivery')

    # get target_BuildDefinitionReferences as a dict ('Name':BuildDefinitionReference)
    our_results.target_build_def_refs = our_client.return_target_build_definition_references_dict()

    # Start storing a results dict that we can use to write to csv later & and also log key build attributes to console
    our_results.results_to_log_dict = our_client.return_key_build_definition_attributes_dict(log=True)

    index = 0
    this_build_as_dict = {}
    this_report_as_dict = {}
    # this_test_run_as_dict = {}
    this_test_run_stats_as_dict = {}

    logger.info('*-------------------------------------------------------------------------------------------------*')
    logger.info('Using above list of build definition ids to get last completed build and test run stats for each...')
    logger.info('*-------------------------------------------------------------------------------------------------*')

    for key, build in our_results.target_build_def_refs.items():
        # get last_completed_build (run) id for each build definition in our 'target' list
        this_def = our_client.get_single_build_definition_by_id(build.id)
        this_build_as_dict['last_comp_build_id'] = this_def.latest_completed_build.id
        this_build_as_dict['last_comp_build_uri'] = this_def.latest_completed_build.uri
        logger.info('---- 1) Gathering last completed build data')
        logger.info('For Build Definition id: %s, name: %s, the last completed buildId is:%s ,'
                    ' last completed build uri is: %s' %
                    (build.id, build.name,  this_build_as_dict['last_comp_build_id'],
                     this_build_as_dict['last_comp_build_uri']))
        our_results.results_to_log_dict[index].update(this_build_as_dict)

        # -----------------------------------------------------------------------------
        # get the report from the last_completed_build - this includes a test results narrative as 'content'
        logger.info('---- 2) Gathering last build report data')
        this_build_report = our_client.get_latest_build_report_by_build_id(build.id)

        # Add the content of the test results to our results dict for the relevant build id
        this_report_as_dict['build_report_html'] = this_build_report.content
        this_report_as_dict['build_report_build_id'] = this_build_report.build_id  # build run id, not the definition id
        our_results.results_to_log_dict[index].update(this_report_as_dict)
        logger.info('Build report retrieved for id: %s' % this_report_as_dict['build_report_build_id'])
        # -----------------------------------------------------------------------------

        logger.info('---- 3) Gathering test run data related to last completed build')
        our_test_client = ADOTestClientObj(creds=BasicAuthentication('PAT', personal_access_token), v6_api=True)
        test_runs_for_this_build_uri =\
            our_test_client.get_test_runs(this_build_as_dict['last_comp_build_uri'], use_v6_api=True)
        # there should always only be one, I think...
        try:
            test_run_obj_for_this_build_uri = test_runs_for_this_build_uri[0]
            # unless there are none...
        except IndexError as e:
            logger.error('No test runs seem to exist for this build.')
            test_run_obj_for_this_build_uri = False

        if test_run_obj_for_this_build_uri:
            # Add the key items we want to a dict
            this_test_run_as_dict = general_utils.add_build_run_details_to_dict(test_run_obj_for_this_build_uri)
            # add the above dict (i.e. test results data for this run) to our results dict
            our_results.results_to_log_dict[index].update(this_test_run_as_dict)
            logger.info(this_test_run_as_dict)
        else:
            this_test_run_as_dict = False

        if this_test_run_as_dict:
            # ----------- get test run statistics - may be overkill, but seems a bit more user friendly that stats above
            logger.info('---- 4) About to get the test run statistics for: %s' % this_test_run_as_dict['test_run_id'])
            one_result = our_test_client.get_test_run_statistics(this_test_run_as_dict['test_run_id'], use_v6_api=True)

            logger.info('Results statistics for run id: %s' % this_test_run_as_dict['test_run_id'])
            stats = one_result.run_statistics
            for this_stat in stats:
                logger.info('For result %s the count is %s' % (this_stat.outcome, this_stat.count))
                stat_key = 'test_run_stat' + this_stat.outcome
                this_test_run_stats_as_dict[stat_key] = this_stat.count

            # add the test results data for this run to our results dict
            our_results.results_to_log_dict[index].update(this_test_run_stats_as_dict)

            # the below could be useful to get attachments in future?
            # our_res_client = ADOTestResultsObj(creds=BasicAuthentication('PAT', personal_access_token), v6_api=True)
            # one_result = our_res_client.get_test_result_log(one_run_id, use_v6_api=True)

        else:
            logger.info('---- No test runs - ** Skipping task 4) ** to get test run statistics for latest run  ----')

        logger.info('------------------------------------------------------')
        index += 1

        # Add the variables associated with each BuildDefinition pipeline and their settings to our results
        # vars_dict = general_utils.reformat_single_definition_vars_dict_for_results(this_def.variables,
        #                                                                            verbose=False)
        # our_results.results_to_log_dict[index].update(vars_dict)

        # # get scheduled build trigger details
        # if this_def.triggers:
        #     triggers_dict =\
        #         general_utils.reformat_single_definition_relevant_triggers_for_results(this_def.triggers,
        #                                                                                verbose=False)
        #     our_results.results_to_log_dict[index].update(triggers_dict)
        # else:
        #     if our_client.verbose_logging:
        #         logger.info('No scheduled trigger for this build.')
        #

    # TODO : the content of the reports we've got need parsed to be useful - each is a massive report...
    # For now, just log one build report html as an example
    logger.info('--------------------------------------------------------')
    logger.info('below used build_report.content to get BuildReportMetadata.content')
    logger.info('WIP - just logging one example result report below here - its a verbose html string for now..')
    logger.info('build_report_html for build defintition id: %s, last_succesful_build id '
                '(build_report_build_id): %s is : %s' %
                (our_results.results_to_log_dict[0]['id'],
                 our_results.results_to_log_dict[0]['build_report_build_id'],
                 our_results.results_to_log_dict[0]['build_report_html']))

    # Write out to csv file
    filename = 'auto_testrunners_report_%s.csv' % args.envt
    general_utils.write_out_report_csv_from_dict(filename, our_results.results_to_log_dict, limit_fieldset=True)
    logger.info('---- CSV file written out: %s' % filename)

    # Close script and log outcomes
    logger.info('------------------------------------------------------')
    logger.info('Script complete.')

    return 0


if __name__ == "__main__":
    exit(main())
