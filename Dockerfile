# Builder docker to create the bioseqdb database
FROM mysql:5.7 as builder
#FROM mysql:5.7
MAINTAINER NMDP Bioinformatics

RUN apt-get update -q

RUN apt install -qy curl python3 python3-pip
# python-mysqldb

COPY requirements.txt /opt/
RUN pip3 install -r /opt/requirements.txt

ARG RELEASES="3310"

# Create `bioseqdb` database and insert sequences
# from IMGT databases
COPY create_imgtdb.py /opt/
RUN echo "Now 1"
RUN ls -la /var/lib/mysql
RUN cat /etc/mysql/my.cnf
RUN /bin/bash -c "/usr/bin/mysqld_safe --initialize --skip-grant-tables &" \
  && sleep 5 \
  && cat /var/lib/mysql/buildkitsandbox.err \
  && mysql -u root -e "set @@global.show_compatibility_56=ON" \
  && mysql -u root -e "CREATE DATABASE bioseqdb" \
  && curl -OL https://raw.githubusercontent.com/biosql/biosql/master/sql/biosqldb-mysql.sql \
  && mysql -u root bioseqdb < biosqldb-mysql.sql \
  && python3 /opt/create_imgtdb.py -v -r $RELEASES \
  && mysqldump -p -u root -p bioseqdb > /opt/biosqldb.sql \
  && mysqladmin shutdown

# Copy the sql dump for the database
FROM mysql:5.7
COPY --from=builder /opt/biosqldb.sql /docker-entrypoint-initdb.d/
