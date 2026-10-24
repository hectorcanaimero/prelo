CREATE TABLE posts (
    id uuid PRIMARY KEY,
    tema text NOT NULL,
    origem text NOT NULL CHECK (origem IN ('editor', 'sugestao')),
    criado_em timestamptz NOT NULL DEFAULT now(),
    estado text NOT NULL
);

CREATE TABLE fontes (
    id bigserial PRIMARY KEY,
    post_id uuid NOT NULL REFERENCES posts (id) ON DELETE CASCADE,
    url text NOT NULL,
    titulo text NOT NULL,
    trecho text NOT NULL
);

CREATE TABLE pecas (
    id uuid PRIMARY KEY,
    post_id uuid NOT NULL REFERENCES posts (id) ON DELETE CASCADE,
    canal text NOT NULL CHECK (canal IN ('blog', 'linkedin', 'instagram')),
    conteudo jsonb NOT NULL DEFAULT '{}',
    violacoes jsonb NOT NULL DEFAULT '[]',
    status text NOT NULL CHECK (status IN ('pendente', 'aprovada', 'agendada', 'publicada', 'descartada')),
    decisao text CHECK (decisao IN ('aprovado', 'editar', 'descartar')),
    comentario text,
    agendada_para timestamptz
);
CREATE INDEX pecas_status_canal ON pecas (status, canal);

CREATE TABLE publicacoes (
    id uuid PRIMARY KEY,
    peca_id uuid NOT NULL REFERENCES pecas (id),
    canal text NOT NULL,
    url text NOT NULL,
    publicada_em timestamptz NOT NULL,
    id_externo text NOT NULL
);

CREATE TABLE custos (
    id bigserial PRIMARY KEY,
    post_id uuid NOT NULL REFERENCES posts (id) ON DELETE CASCADE,
    agente text NOT NULL,
    modelo text NOT NULL,
    tokens_entrada integer NOT NULL,
    tokens_saida integer NOT NULL,
    usd numeric(12, 6) NOT NULL,
    criado_em timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX custos_post ON custos (post_id);
