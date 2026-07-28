// Mapping version: v1-draft. Run only after M0 mapping review.
CREATE CONSTRAINT knowledge_object_id_unique IF NOT EXISTS
FOR (node:KnowledgeObject) REQUIRE node.object_id IS UNIQUE;

CREATE CONSTRAINT claim_id_unique IF NOT EXISTS
FOR (node:Claim) REQUIRE node.claim_id IS UNIQUE;

CREATE CONSTRAINT decision_id_unique IF NOT EXISTS
FOR (node:Decision) REQUIRE node.decision_id IS UNIQUE;

CREATE CONSTRAINT evidence_id_unique IF NOT EXISTS
FOR (node:Evidence) REQUIRE node.evidence_id IS UNIQUE;

CREATE CONSTRAINT source_document_id_unique IF NOT EXISTS
FOR (node:SourceDocument) REQUIRE node.source_document_id IS UNIQUE;
