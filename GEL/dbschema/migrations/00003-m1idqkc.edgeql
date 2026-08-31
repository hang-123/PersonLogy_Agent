CREATE MIGRATION m1idqkclmx43e5peunodiaw2s7nd6yg4bzccok6z5td2l25ap63ona
    ONTO m15svfscdtglr7xjqwurn5pkpvot5pu7newuy4wuljmpt4oz2y2crq
{
  CREATE TYPE default::AuditChainHead {
      CREATE PROPERTY event_hash: std::str;
      CREATE REQUIRED PROPERTY key: std::str {
          CREATE CONSTRAINT std::exclusive;
      };
      CREATE REQUIRED PROPERTY sequence: std::int64 {
          SET default := 0;
      };
  };
  CREATE TYPE default::AuditEvent EXTENDING default::Timestamped {
      CREATE PROPERTY actor_id: std::str;
      CREATE REQUIRED PROPERTY actor_type: std::str;
      CREATE PROPERTY after_digest: std::str;
      CREATE PROPERTY before_digest: std::str;
      CREATE PROPERTY entity_id: std::str;
      CREATE REQUIRED PROPERTY entity_type: std::str;
      CREATE REQUIRED PROPERTY event_hash: std::str {
          CREATE CONSTRAINT std::exclusive;
      };
      CREATE REQUIRED PROPERTY event_type: std::str;
      CREATE REQUIRED PROPERTY metadata: std::json {
          SET default := (<std::json>{});
      };
      CREATE PROPERTY parent_span_id: std::str;
      CREATE PROPERTY prev_hash: std::str;
      CREATE PROPERTY project_id: std::uuid;
      CREATE PROPERTY reason_code: std::str;
      CREATE PROPERTY request_id: std::str;
      CREATE REQUIRED PROPERTY schema_version: std::str;
      CREATE REQUIRED PROPERTY sequence: std::int64 {
          CREATE CONSTRAINT std::exclusive;
      };
      CREATE PROPERTY span_id: std::str;
      CREATE REQUIRED PROPERTY status: std::str;
      CREATE REQUIRED PROPERTY trace_id: std::str;
  };
};
