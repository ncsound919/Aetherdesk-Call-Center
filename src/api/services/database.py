"""Database layer — re-exports from focused modules."""
from contextlib import contextmanager

from api.services.db_ai_assist import (
    create_knowledge_snippet_db,
    delete_knowledge_snippet_db,
    list_knowledge_snippets_db,
    search_knowledge_snippets_db,
)
from api.services.db_ai_evaluation import (
    create_evaluation_db,
    create_experiment_db,
    get_accuracy_metrics_db,
    get_confidence_distribution_db,
    get_experiment_db,
    list_evaluations_db,
    list_experiments_db,
    update_experiment_db,
)
from api.services.db_ai_platform import (
    create_dataset_db,
    create_emotion_log_db,
    create_eval_metrics_db,
    create_external_job_db,
    create_label_db,
    create_model_audit_log_db,
    create_model_db,
    create_training_job_db,
    create_turn_db,
    create_voice_profile_db,
    get_active_model_db,
    get_dataset_db,
    get_emotion_trends_db,
    get_eval_metrics_db,
    get_model_audit_log_db,
    get_model_db,
    get_model_version_db,
    get_training_job_db,
    list_datasets_db,
    list_external_jobs_db,
    list_labels_db,
    list_models_db,
    list_training_jobs_db,
    list_turns_db,
    list_voice_profiles_db,
    promote_model_db,
    rollback_model_db,
    update_dataset_db,
    update_training_job_db,
)
from api.services.db_audio_quality import (
    create_quality_metric_db,
    get_call_quality_db,
    get_quality_summary_db,
    get_quality_trends_db,
    list_quality_metrics_db,
)
from api.services.db_bc import (
    create_backup_channel_db,
    create_chaos_experiment_db,
    create_contract_db,
    create_failover_test_db,
    get_contract_alerts_db,
    list_backup_channels_db,
    list_chaos_experiments_db,
    list_contracts_db,
    list_failover_tests_db,
    update_backup_channel_test_db,
    update_chaos_experiment_db,
)
from api.services.db_calls import (
    create_call_session,
    dequeue_call,
    enqueue_call,
    get_billing_summary,
    get_call_session,
    get_order_status_db,
    get_pending_approvals_db,
    get_saas_dashboard_db,
    get_session_recordings_db,
    get_usage_stats,
    get_webhook_url_db,
    list_calls,
    log_audit_event,
    lookup_invoice_db,
    process_approval_db,
    rent_agent_db,
    update_call_status,
)
from api.services.db_cdp import (
    create_customer_interaction_db,
    create_customer_profile_db,
    create_segment_db,
    find_customers_by_identifier_db,
    get_customer_profile_db,
    get_customer_tags_db,
    get_segment_db,
    list_csat_surveys_for_customer_db,
    list_customer_interactions_db,
    list_segments_db,
    search_customers_db,
    update_customer_tags_db,
    update_segment_member_count_db,
    upsert_customer_profile_db,
)
from api.services.db_config import (
    DATABASE_URL,
    SQLITE_PATH,
    SQLITE_POOL_SIZE,
    SQLITE_TIMEOUT,
    USE_POSTGRES,
)
from api.services.db_cx import (
    create_survey_db,
    get_csat_score_db,
    get_customer_360_db,
    get_nps_score_db,
    get_response_rate_db,
    get_sentiment_trends_db,
    list_surveys_db,
)
from api.services.db_data_lineage import (
    create_lineage_entry_db,
    get_column_lineage_db,
    get_data_health_score_db,
    get_lineage_graph_db,
    get_record_lineage_db,
)
from api.services.db_developer import (
    create_api_key_db,
    create_webhook_delivery_log_db,
    get_active_webhooks_for_event_db,
    get_api_key_by_id_db,
    get_api_key_by_prefix_db,
    get_webhook_by_id_db,
    get_webhook_delivery_log_by_id_db,
    get_webhook_delivery_logs_db,
    list_api_keys_db,
    list_webhooks_db,
    register_webhook_db,
    revoke_api_key_db,
    unregister_webhook_db,
    update_api_key_last_used_db,
    update_webhook_delivery_log_db,
)
from api.services.db_enterprise import (
    create_api_version_db,
    create_conversation_quality_score_db,
    create_customer_portal_session_db,
    get_api_versions_db,
    get_customer_portal_session_db,
    list_conversation_quality_scores_db,
    update_api_version_status_db,
)
from api.services.db_errors import (
    DatabaseError,
    NotFoundError,
    PoolNotAvailableError,
)
from api.services.db_integrations import (
    create_integration_config_db,
    create_ticket_sync_log_db,
    get_integration_config_db,
    list_integration_configs_db,
    list_ticket_sync_logs_db,
    update_integration_config_db,
)
from api.services.db_omnichannel import (
    add_chat_message_db,
    create_chat_session_db,
    create_sms_template_db,
    get_chat_messages_db,
    get_chat_session_db,
    list_sms_log_db,
    list_sms_templates_db,
    list_waiting_sessions_db,
    log_sms_db,
    update_chat_session_db,
)
from api.services.db_pool import (
    _get_sqlite_conn,
    close_pg_pool,
    db_context,
    decrypt_val,
    encrypt_val,
    get_pg_pool,
)
from api.services.db_reliability import (
    create_dr_test_db,
    get_dr_test_db,
    get_rate_limit_config_db,
    list_circuit_breaker_events_db,
    list_dr_tests_db,
    list_rate_limit_configs_db,
    log_circuit_breaker_event_db,
    set_rate_limit_config_db,
)
from api.services.db_schema import (
    SCHEMA_SQL,
    SQLITE_SCHEMA_SQL,
    init_pg_schema,
    init_sqlite_schema,
)
from api.services.db_security import (
    create_pen_test_scan_db,
    create_rbac_audit_result_db,
    create_waf_event_db,
    get_data_classification_db,
    get_pen_test_scan_db,
    list_pen_test_scans_db,
    list_rbac_audit_results_db,
    list_waf_events_db,
    set_data_classification_db,
    update_pen_test_scan_db,
)
from api.services.db_tenants import (
    create_agent,
    create_agent_profile_db,
    create_tenant,
    delete_agent_db,
    get_agent_db,
    get_available_agents,
    get_tenant_by_api_key,
    get_tenant_db,
    get_tenant_settings_db,
    get_user_by_email_db,
    list_agents,
    list_tenants_db,
    update_agent_db,
    update_agent_status,
    update_tenant_settings_db,
    verify_tenant_api_key,
)
from api.services.db_wfm import (
    create_qa_rubric_db,
    create_qa_score_db,
    create_schedule_db,
    create_shift_db,
    delete_shift_db,
    get_agent_qa_summary_db,
    get_call_volume_history_db,
    get_schedule_db,
    list_qa_rubrics_db,
    list_qa_scores_db,
    list_schedules_db,
    list_shifts_db,
    update_schedule_adherence_db,
    update_shift_db,
)
from api.services.db_wfm_metrics import (
    create_aht_db,
    create_csat_db,
    create_fcr_db,
    create_nps_db,
    get_aht_stats_db,
    get_csat_trend_db,
    get_fcr_stats_db,
    get_nps_stats_db,
)


@contextmanager
def db_context_sync():
    if USE_POSTGRES:
        raise RuntimeError("db_context_sync not supported for PostgreSQL. Use async db_context instead.")
    conn = _get_sqlite_conn()
    try:
        yield conn
    finally:
        conn.close()


async def db_run_sync(db_func):
    """Run a synchronous DB function in a thread to avoid blocking the event loop."""
    import asyncio
    return await asyncio.to_thread(db_func)


__all__ = [
    "db_context", "db_context_sync",
    "get_pg_pool", "close_pg_pool",
    "encrypt_val", "decrypt_val",
    "USE_POSTGRES", "DATABASE_URL", "SQLITE_PATH", "SQLITE_POOL_SIZE", "SQLITE_TIMEOUT",
    "SCHEMA_SQL", "SQLITE_SCHEMA_SQL",
    "init_pg_schema", "init_sqlite_schema",
    "create_tenant", "get_tenant_db", "list_tenants_db",
    "get_tenant_by_api_key", "verify_tenant_api_key",
    "get_user_by_email_db",
    "get_tenant_settings_db", "update_tenant_settings_db",
    "create_agent", "get_agent_db", "list_agents",
    "update_agent_status", "update_agent_db", "delete_agent_db",
    "get_available_agents", "create_agent_profile_db",
    "create_call_session", "get_call_session", "update_call_status", "list_calls",
    "enqueue_call", "dequeue_call",
    "get_usage_stats", "get_billing_summary",
    "log_audit_event",
    "get_saas_dashboard_db", "rent_agent_db",
    "get_session_recordings_db", "get_pending_approvals_db",
    "process_approval_db",
    "get_webhook_url_db", "lookup_invoice_db", "get_order_status_db",
    "DatabaseError", "NotFoundError", "PoolNotAvailableError",
    "create_shift_db", "list_shifts_db", "update_shift_db", "delete_shift_db",
    "create_schedule_db", "get_schedule_db", "list_schedules_db", "update_schedule_adherence_db",
    "create_qa_rubric_db", "list_qa_rubrics_db", "create_qa_score_db", "list_qa_scores_db",
    "get_agent_qa_summary_db", "get_call_volume_history_db",
    "create_quality_metric_db", "list_quality_metrics_db",
    "get_quality_summary_db", "get_quality_trends_db", "get_call_quality_db",
    "create_evaluation_db", "list_evaluations_db",
    "get_accuracy_metrics_db", "create_experiment_db",
    "list_experiments_db", "get_experiment_db",
    "update_experiment_db", "get_confidence_distribution_db",
    "create_survey_db", "list_surveys_db",
    "get_csat_score_db", "get_response_rate_db", "get_nps_score_db",
    "get_sentiment_trends_db", "get_customer_360_db",
    "create_integration_config_db", "list_integration_configs_db",
    "get_integration_config_db", "update_integration_config_db",
    "create_ticket_sync_log_db", "list_ticket_sync_logs_db",
    "create_sms_template_db", "list_sms_templates_db",
    "log_sms_db", "list_sms_log_db",
    "create_chat_session_db", "get_chat_session_db",
    "list_waiting_sessions_db", "add_chat_message_db",
    "get_chat_messages_db", "update_chat_session_db",
    "create_knowledge_snippet_db", "search_knowledge_snippets_db",
    "list_knowledge_snippets_db", "delete_knowledge_snippet_db",
    "create_lineage_entry_db", "get_record_lineage_db",
    "get_lineage_graph_db", "get_column_lineage_db",
    "get_data_health_score_db",
    # AI Platform
    "create_model_db", "list_models_db", "get_model_db", "get_model_version_db",
    "promote_model_db", "rollback_model_db", "get_active_model_db",
    "create_training_job_db", "get_training_job_db", "list_training_jobs_db", "update_training_job_db",
    "create_voice_profile_db", "list_voice_profiles_db",
    "create_emotion_log_db", "get_emotion_trends_db",
    "create_dataset_db", "list_datasets_db", "get_dataset_db", "update_dataset_db",
    "create_turn_db", "list_turns_db",
    "create_label_db", "list_labels_db",
    "create_external_job_db", "list_external_jobs_db",
    "create_model_audit_log_db", "get_model_audit_log_db",
    "create_eval_metrics_db", "get_eval_metrics_db",
    # WFM Metrics
    "create_aht_db", "create_fcr_db", "create_csat_db", "create_nps_db",
    "get_aht_stats_db", "get_fcr_stats_db", "get_csat_trend_db", "get_nps_stats_db",
    # BC
    "create_failover_test_db", "list_failover_tests_db",
    "create_chaos_experiment_db", "update_chaos_experiment_db", "list_chaos_experiments_db",
    "create_contract_db", "list_contracts_db", "get_contract_alerts_db",
    "create_backup_channel_db", "list_backup_channels_db", "update_backup_channel_test_db",
    # Enterprise
    "create_conversation_quality_score_db", "list_conversation_quality_scores_db",
    "create_api_version_db", "get_api_versions_db", "update_api_version_status_db",
    "create_customer_portal_session_db", "get_customer_portal_session_db",
    # Security
    "create_pen_test_scan_db", "list_pen_test_scans_db",
    "get_pen_test_scan_db", "update_pen_test_scan_db",
    "create_waf_event_db", "list_waf_events_db",
    "set_data_classification_db", "get_data_classification_db",
    "create_rbac_audit_result_db", "list_rbac_audit_results_db",
    # Reliability
    "create_dr_test_db", "list_dr_tests_db", "get_dr_test_db",
    "get_rate_limit_config_db", "set_rate_limit_config_db",
    "list_rate_limit_configs_db",
    "log_circuit_breaker_event_db", "list_circuit_breaker_events_db",
    # Developer
    "create_api_key_db", "revoke_api_key_db", "list_api_keys_db",
    "get_api_key_by_prefix_db", "get_api_key_by_id_db", "update_api_key_last_used_db",
    "register_webhook_db", "unregister_webhook_db", "list_webhooks_db",
    "get_webhook_by_id_db", "get_active_webhooks_for_event_db",
    "create_webhook_delivery_log_db", "update_webhook_delivery_log_db",
    "get_webhook_delivery_logs_db", "get_webhook_delivery_log_by_id_db",
    # CDP
    "create_customer_profile_db", "get_customer_profile_db",
    "upsert_customer_profile_db", "find_customers_by_identifier_db",
    "search_customers_db", "update_customer_tags_db", "get_customer_tags_db",
    "list_customer_interactions_db", "create_customer_interaction_db",
    "list_csat_surveys_for_customer_db",
    "create_segment_db", "list_segments_db", "get_segment_db",
    "update_segment_member_count_db",
]


