# NUT casa — add-on per Home Assistant

Accendere e spegnere i NAS QNAP da Home Assistant, con un interruttore per NAS, e ricevere i loro eventi via syslog.

- Spegnimento pulito tramite un **UPS finto** (protocollo NUT) che risponde a ogni NAS in base al suo IP.
- Accensione con **Wake-on-LAN**, stato con il **ping**.
- Eventi di QTS (syslog) come sensori ed eventi in HA, più uno storico su file.

*Turn QNAP NAS units on and off from Home Assistant: a fake NUT UPS answering per client IP, Wake-on-LAN, and QTS syslog events as MQTT entities. Documentation in Italian.*

## Installazione
1. *Impostazioni → Componenti aggiuntivi → Negozio → ⋮ → Repository*: aggiungere `https://github.com/samusamu81/nut-casa`.
2. Installare **NUT casa**, compilare l'elenco dei NAS nella scheda *Configurazione*, avviare.

Documentazione completa: [nut_casa/DOCS.md](nut_casa/DOCS.md). Licenza [MIT](LICENSE).
