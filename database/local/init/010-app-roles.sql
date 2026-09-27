-- Values arrive from the local Compose environment and are quoted as SQL
-- literals by psql's :'variable' expansion; they are never interpolated by a
-- shell or written to logs.
\getenv migrator_password LOCAL_CAMPAIGN_MIGRATOR_PASSWORD
\getenv runtime_password LOCAL_CAMPAIGN_RUNTIME_PASSWORD
\getenv operator_password LOCAL_CAMPAIGN_OPERATOR_PASSWORD

CREATE ROLE campaign_migrator WITH
  LOGIN PASSWORD :'migrator_password'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE ROLE campaign_runtime WITH
  LOGIN PASSWORD :'runtime_password'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE ROLE campaign_operator WITH
  LOGIN PASSWORD :'operator_password'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;

ALTER DATABASE campaigns OWNER TO campaign_migrator;
REVOKE CONNECT, TEMPORARY ON DATABASE campaigns FROM PUBLIC;
GRANT CONNECT ON DATABASE campaigns
  TO campaign_migrator, campaign_runtime, campaign_operator;

-- The image's bootstrap superuser is only needed during initialization.
ALTER ROLE campaign_bootstrap NOLOGIN;
