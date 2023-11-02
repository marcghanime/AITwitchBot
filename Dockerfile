FROM python:3.11.6

# Install Chrome
RUN apt-get update && apt-get install -y wget gnupg2 curl unzip jq libpulse-dev

RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -
RUN echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list
RUN apt-get update && apt-get install -y google-chrome-stable

RUN wget https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/$(curl -sS https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions.json | jq -r '.channels.Stable.version')/linux64/chromedriver-linux64.zip
RUN unzip chromedriver-linux64.zip
RUN mv chromedriver-linux64/chromedriver /usr/local/bin/

# Audio Setup
RUN mkdir -p /var/run/dbus
RUN dbus-uuidgen > /var/lib/dbus/machine-id
RUN dbus-daemon --config-file=/usr/share/dbus-1/system.conf --print-address

# Make directory
RUN git clone -b experimental https://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@github.com/marcghanime/TwitchBot.git

# Copy files
COPY config.json /TwitchBot

# Set working directory
WORKDIR /TwitchBot

# Install requirements
RUN pip install --default-timeout=100 -r requirements.txt

# Setup
RUN python setup.py

# Run
CMD python main.py
