FROM ubuntu:22.04
RUN apt-get update -qq && apt-get install -y -qq python3 bubblewrap sudo procps acl >/dev/null
RUN useradd -m runner && useradd -r -M -s /bin/sh _guardrun && chmod 755 /home/runner \
 && echo 'runner ALL=(_guardrun) NOPASSWD: ALL' > /etc/sudoers.d/gr && echo 'runner ALL=(root) NOPASSWD: ALL' >> /etc/sudoers.d/gr
USER runner
WORKDIR /home/runner
