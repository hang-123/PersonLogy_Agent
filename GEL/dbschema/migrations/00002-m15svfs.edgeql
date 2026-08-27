CREATE MIGRATION m15svfscdtglr7xjqwurn5pkpvot5pu7newuy4wuljmpt4oz2y2crq
    ONTO m1kj56kpphqgibqetwda5fugpczli7za4stno63xvjjr3d6u45zcka
{
  CREATE SCALAR TYPE default::CandidateKind EXTENDING enum<node, claim, relation>;
  CREATE SCALAR TYPE default::GovernanceIssueSeverity EXTENDING enum<info, warning, error>;
  CREATE SCALAR TYPE default::GovernanceRunStatus EXTENDING enum<passed, needs_review, rejected>;
  CREATE SCALAR TYPE default::ReviewTaskStatus EXTENDING enum<pending, approved, rejected, revised>;
  ALTER TYPE default::Citation {
      CREATE REQUIRED PROPERTY metadata: std::json {
          SET default := (<std::json>{});
      };
  };
  ALTER TYPE default::Claim {
      CREATE REQUIRED PROPERTY metadata: std::json {
          SET default := (<std::json>{});
      };
  };
  CREATE TYPE default::ConflictRecord EXTENDING default::Timestamped {
      CREATE REQUIRED LINK project: default::Project;
      CREATE REQUIRED PROPERTY basis: std::str;
      CREATE REQUIRED MULTI PROPERTY candidate_ids: std::uuid;
      CREATE REQUIRED PROPERTY status: std::str {
          SET default := 'open';
      };
  };
  CREATE TYPE default::DuplicateGroup EXTENDING default::Timestamped {
      CREATE REQUIRED LINK project: default::Project;
      CREATE REQUIRED PROPERTY basis: std::str;
      CREATE REQUIRED MULTI PROPERTY candidate_ids: std::uuid;
  };
  CREATE TYPE default::GovernanceRun EXTENDING default::Timestamped {
      CREATE REQUIRED LINK project: default::Project;
      CREATE REQUIRED MULTI PROPERTY candidate_ids: std::uuid;
      CREATE REQUIRED PROPERTY rule_version: std::str;
      CREATE REQUIRED PROPERTY status: default::GovernanceRunStatus;
      CREATE REQUIRED PROPERTY task_id: std::uuid;
  };
  CREATE TYPE default::GovernanceIssue EXTENDING default::Timestamped {
      CREATE REQUIRED LINK run: default::GovernanceRun;
      CREATE REQUIRED PROPERTY candidate_id: std::uuid;
      CREATE REQUIRED PROPERTY candidate_kind: default::CandidateKind;
      CREATE REQUIRED PROPERTY code: std::str;
      CREATE REQUIRED PROPERTY message: std::str;
      CREATE REQUIRED PROPERTY severity: default::GovernanceIssueSeverity;
  };
  CREATE TYPE default::ReviewTask EXTENDING default::Timestamped {
      CREATE REQUIRED LINK run: default::GovernanceRun;
      CREATE REQUIRED PROPERTY after: std::json {
          SET default := (<std::json>{});
      };
      CREATE REQUIRED PROPERTY before: std::json {
          SET default := (<std::json>{});
      };
      CREATE REQUIRED PROPERTY candidate_id: std::uuid;
      CREATE REQUIRED PROPERTY candidate_kind: default::CandidateKind;
      CREATE PROPERTY reason: std::str;
      CREATE PROPERTY reviewed_at: std::datetime;
      CREATE PROPERTY reviewer_id: std::str;
      CREATE REQUIRED PROPERTY status: default::ReviewTaskStatus {
          SET default := (default::ReviewTaskStatus.pending);
      };
      CREATE REQUIRED PROPERTY version: std::int32 {
          SET default := 1;
          CREATE CONSTRAINT std::min_value(1);
      };
  };
  ALTER TYPE default::Relation {
      CREATE REQUIRED PROPERTY metadata: std::json {
          SET default := (<std::json>{});
      };
      CREATE REQUIRED PROPERTY status: default::VerificationStatus {
          SET default := (default::VerificationStatus.candidate);
      };
  };
  ALTER SCALAR TYPE default::VerificationStatus EXTENDING enum<candidate, machine_checked, pending_review, needs_revision, human_verified, ready_for_writeback, rejected>;
};
