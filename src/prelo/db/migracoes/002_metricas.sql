CREATE TABLE metricas (
    id bigserial PRIMARY KEY,
    publicacao_id uuid NOT NULL REFERENCES publicacoes (id) ON DELETE CASCADE,
    coletada_em timestamptz NOT NULL DEFAULT now(),
    reacoes integer NOT NULL,
    comentarios jsonb NOT NULL DEFAULT '[]'
);
CREATE INDEX metricas_publicacao ON metricas (publicacao_id, coletada_em DESC);
