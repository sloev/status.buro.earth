start:
	docker-compose -f docker-compose.test.yml up --build

daemon:
	docker-compose up --build -d