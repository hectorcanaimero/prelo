-- Llamadas al modelo fuera de un post (conversación en Slack, sugerencias de temas) también tienen costo.
ALTER TABLE custos ALTER COLUMN post_id DROP NOT NULL;
