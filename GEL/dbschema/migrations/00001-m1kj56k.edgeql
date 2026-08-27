CREATE MIGRATION m1kj56kpphqgibqetwda5fugpczli7za4stno63xvjjr3d6u45zcka
    ONTO initial
{
  CREATE SCALAR TYPE default::JobStatus EXTENDING enum<queued, running, retrying, succeeded, failed, cancelled>;
  CREATE SCALAR TYPE default::ReviewDecision EXTENDING enum<approved, rejected, revised>;
  CREATE SCALAR TYPE default::SourceKind EXTENDING enum<pdf, conversation>;
  CREATE SCALAR TYPE default::VerificationStatus EXTENDING enum<candidate, machine_checked, human_verified, rejected>;
  CREATE FUTURE no_linkful_computed_splats;
  CREATE ABSTRACT TYPE default::Timestamped {
      CREATE REQUIRED PROPERTY created_at: std::datetime {
          SET default := (std::datetime_current());
      };
  };
  CREATE TYPE default::Project EXTENDING default::Timestamped {
      CREATE REQUIRED PROPERTY name: std::str;
      CREATE REQUIRED PROPERTY slug: std::str {
          CREATE CONSTRAINT std::exclusive;
      };
  };
  CREATE TYPE default::Source EXTENDING default::Timestamped {
      CREATE REQUIRED LINK project: default::Project;
      CREATE REQUIRED PROPERTY kind: default::SourceKind;
      CREATE REQUIRED PROPERTY title: std::str;
  };
  CREATE TYPE default::SourceVersion EXTENDING default::Timestamped {
      CREATE REQUIRED LINK source: default::Source;
      CREATE REQUIRED PROPERTY content_hash: std::str;
      CREATE CONSTRAINT std::exclusive ON ((.source, .content_hash));
      CREATE REQUIRED PROPERTY version: std::int16 {
          CREATE CONSTRAINT std::min_value(1);
      };
      CREATE CONSTRAINT std::exclusive ON ((.source, .version));
      CREATE REQUIRED PROPERTY object_key: std::str;
  };
  CREATE TYPE default::ContentBlock EXTENDING default::Timestamped {
      CREATE REQUIRED LINK source_version: default::SourceVersion;
      CREATE REQUIRED PROPERTY ordinal: std::int32 {
          CREATE CONSTRAINT std::min_value(0);
      };
      CREATE CONSTRAINT std::exclusive ON ((.source_version, .ordinal));
      CREATE REQUIRED PROPERTY content: std::str;
      CREATE REQUIRED PROPERTY content_hash: std::str;
      CREATE REQUIRED PROPERTY locator: std::json {
          SET default := (<std::json>{});
      };
  };
  CREATE TYPE default::Citation EXTENDING default::Timestamped {
      CREATE REQUIRED LINK content_block: default::ContentBlock;
      CREATE REQUIRED PROPERTY locator: std::json {
          SET default := (<std::json>{});
      };
      CREATE REQUIRED PROPERTY quote: std::str;
  };
  CREATE TYPE default::KnowledgeNode EXTENDING default::Timestamped {
      CREATE REQUIRED LINK project: default::Project;
      CREATE REQUIRED PROPERTY node_type: std::str;
      CREATE REQUIRED PROPERTY properties: std::json {
          SET default := (<std::json>{});
      };
      CREATE REQUIRED PROPERTY status: default::VerificationStatus {
          SET default := (default::VerificationStatus.candidate);
      };
      CREATE REQUIRED PROPERTY title: std::str;
  };
  CREATE TYPE default::Claim EXTENDING default::Timestamped {
      CREATE REQUIRED MULTI LINK citations: default::Citation;
      CREATE REQUIRED LINK project: default::Project;
      CREATE REQUIRED LINK subject: default::KnowledgeNode;
      CREATE PROPERTY confidence: std::float32 {
          CREATE CONSTRAINT std::max_value(1);
          CREATE CONSTRAINT std::min_value(0);
      };
      CREATE REQUIRED PROPERTY statement: std::str;
      CREATE REQUIRED PROPERTY status: default::VerificationStatus {
          SET default := (default::VerificationStatus.candidate);
      };
  };
  CREATE TYPE default::RelationType EXTENDING default::Timestamped {
      CREATE REQUIRED PROPERTY description: std::str {
          SET default := '';
      };
      CREATE REQUIRED PROPERTY directional: std::bool {
          SET default := true;
      };
      CREATE REQUIRED PROPERTY key: std::str {
          CREATE CONSTRAINT std::exclusive;
      };
      CREATE REQUIRED PROPERTY label: std::str;
  };
  CREATE TYPE default::Relation EXTENDING default::Timestamped {
      CREATE REQUIRED MULTI LINK citations: default::Citation;
      CREATE REQUIRED LINK source: default::KnowledgeNode;
      CREATE REQUIRED LINK target: default::KnowledgeNode;
      CREATE REQUIRED LINK project: default::Project;
      CREATE REQUIRED LINK relation_type: default::RelationType;
      CREATE PROPERTY confidence: std::float32 {
          CREATE CONSTRAINT std::max_value(1);
          CREATE CONSTRAINT std::min_value(0);
      };
      CREATE REQUIRED PROPERTY properties: std::json {
          SET default := (<std::json>{});
      };
  };
  CREATE TYPE default::Job EXTENDING default::Timestamped {
      CREATE REQUIRED PROPERTY attempt: std::int16 {
          SET default := 0;
          CREATE CONSTRAINT std::min_value(0);
      };
      CREATE PROPERTY failure_reason: std::str;
      CREATE PROPERTY finished_at: std::datetime;
      CREATE REQUIRED PROPERTY idempotency_key: std::str {
          CREATE CONSTRAINT std::exclusive;
      };
      CREATE REQUIRED PROPERTY kind: std::str;
      CREATE REQUIRED PROPERTY max_attempts: std::int16 {
          SET default := 3;
          CREATE CONSTRAINT std::min_value(1);
      };
      CREATE PROPERTY next_attempt_at: std::datetime;
      CREATE REQUIRED PROPERTY payload: std::json {
          SET default := (<std::json>{});
      };
      CREATE REQUIRED PROPERTY progress: std::int16 {
          SET default := 0;
          CREATE CONSTRAINT std::max_value(100);
          CREATE CONSTRAINT std::min_value(0);
      };
      CREATE REQUIRED PROPERTY stage: std::str {
          SET default := 'queued';
      };
      CREATE PROPERTY started_at: std::datetime;
      CREATE REQUIRED PROPERTY status: default::JobStatus {
          SET default := (default::JobStatus.queued);
      };
      CREATE REQUIRED PROPERTY timeout_seconds: std::int32 {
          SET default := 900;
          CREATE CONSTRAINT std::min_value(1);
      };
  };
  CREATE TYPE default::ReviewRecord EXTENDING default::Timestamped {
      CREATE REQUIRED PROPERTY after: std::json {
          SET default := (<std::json>{});
      };
      CREATE REQUIRED PROPERTY before: std::json {
          SET default := (<std::json>{});
      };
      CREATE REQUIRED PROPERTY decision: default::ReviewDecision;
      CREATE REQUIRED PROPERTY note: std::str {
          SET default := '';
      };
      CREATE REQUIRED PROPERTY reviewer_id: std::str;
      CREATE REQUIRED PROPERTY target_id: std::uuid;
  };
};
