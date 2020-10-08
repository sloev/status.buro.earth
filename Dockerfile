FROM python:latest


RUN apt-get update && apt-get install gifsicle && \
    pip install poetry

ADD pyproject.toml .
ADD poetry.lock poetry.lock

RUN poetry install

ADD statusburo/ statusburo/

EXPOSE 9002

CMD ["poetry", "run", "start"]
