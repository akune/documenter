COMPOSE = docker compose -f tests/integration/docker-compose.test.yml

.PHONY: test-integration test-integration-up test-integration-down test-integration-logs

test-integration: test-integration-up
	pytest tests/integration/ -v
	$(MAKE) test-integration-down

test-integration-up:
	$(COMPOSE) up -d --wait paperless nextcloud paperless-redis
	$(COMPOSE) up -d test-init
	$(COMPOSE) wait test-init

test-integration-down:
	$(COMPOSE) down -v

test-integration-logs:
	$(COMPOSE) logs
