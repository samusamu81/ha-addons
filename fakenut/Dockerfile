ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache nut jq python3 py3-paho-mqtt tzdata

COPY run.sh fakenut.py /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
