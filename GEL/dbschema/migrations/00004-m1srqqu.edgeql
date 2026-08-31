CREATE MIGRATION m1srqqu5j72u2qwzr5yvp256k5xzxhaai5l65mbjvlr6rpkdkih7gq
    ONTO m1idqkclmx43e5peunodiaw2s7nd6yg4bzccok6z5td2l25ap63ona
{
  CREATE SCALAR TYPE default::WritebackStatus EXTENDING enum<effects_pending, retryable_failed, completed, reverted>;
  CREATE TYPE default::Conversation EXTENDING default::Timestamped {
      CREATE REQUIRED LINK project: default::Project;
      CREATE REQUIRED PROPERTY external_id: std::str;
      CREATE CONSTRAINT std::exclusive ON ((.project, .external_id));
      CREATE REQUIRED LINK source: default::Source;
      CREATE REQUIRED PROPERTY metadata: std::json {
          SET default := (<std::json>{});
      };
      CREATE REQUIRED PROPERTY title: std::str;
  };
  CREATE TYPE default::ConversationMessage EXTENDING default::Timestamped {
      CREATE REQUIRED LINK conversation: default::Conversation;
      CREATE REQUIRED PROPERTY external_id: std::str;
      CREATE CONSTRAINT std::exclusive ON ((.conversation, .external_id));
      CREATE REQUIRED PROPERTY attachments: std::json {
          SET default := (<std::json>{});
      };
      CREATE REQUIRED PROPERTY content: std::str;
      CREATE REQUIRED PROPERTY content_hash: std::str;
      CREATE REQUIRED PROPERTY ordinal: std::int32 {
          CREATE CONSTRAINT std::min_value(0);
      };
      CREATE PROPERTY parent_external_id: std::str;
      CREATE REQUIRED PROPERTY role: std::str;
  };
  CREATE TYPE default::WritebackRecord EXTENDING default::Timestamped {
      CREATE REQUIRED LINK governance_run: default::GovernanceRun;
      CREATE REQUIRED LINK project: default::Project;
      CREATE REQUIRED PROPERTY candidate_digest: std::str;
      CREATE REQUIRED PROPERTY candidates: std::json {
          SET default := (<std::json>{});
      };
      CREATE PROPERTY committed_at: std::datetime;
      CREATE PROPERTY completed_at: std::datetime;
      CREATE PROPERTY effects_job_id: std::uuid;
      CREATE PROPERTY error_code: std::str;
      CREATE PROPERTY error_digest: std::str;
      CREATE REQUIRED PROPERTY idempotency_key: std::str {
          CREATE CONSTRAINT std::exclusive;
      };
      CREATE PROPERTY index_job_id: std::uuid;
      CREATE PROPERTY okf_object_key: std::str;
      CREATE REQUIRED PROPERTY request_digest: std::str;
      CREATE REQUIRED PROPERTY schema_namespace: std::str;
      CREATE REQUIRED PROPERTY schema_version: std::int32 {
          CREATE CONSTRAINT std::min_value(1);
      };
      CREATE REQUIRED PROPERTY status: default::WritebackStatus {
          SET default := (default::WritebackStatus.effects_pending);
      };
  };
  CREATE TYPE default::WritebackItem EXTENDING default::Timestamped {
      CREATE REQUIRED LINK record: default::WritebackRecord;
      CREATE REQUIRED PROPERTY after_digest: std::str;
      CREATE REQUIRED PROPERTY after_status: default::VerificationStatus;
      CREATE REQUIRED PROPERTY before_digest: std::str;
      CREATE REQUIRED PROPERTY before_status: default::VerificationStatus;
      CREATE REQUIRED PROPERTY candidate_id: std::uuid;
      CREATE REQUIRED PROPERTY candidate_kind: default::CandidateKind;
      CREATE REQUIRED PROPERTY result: std::str;
  };
};
