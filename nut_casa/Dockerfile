ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache nut jq python3 py3-paho-mqtt tzdata

COPY run.sh nut_casa.py /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
