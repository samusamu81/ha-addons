ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache python3 py3-paho-mqtt tzdata

COPY qlog2ha.py /
CMD [ "python3", "-u", "/qlog2ha.py" ]
