#!/usr/bin/env bash
COMMON_PKGS="vim software-properties-common git tmux cron"
SDKMAN_DEPS="curl unzip zip"
export DEBIAN_FRONTEND=noninteractive

update_and_install_common_pks() {
    sudo apt -yqq update && sudo apt -yqq upgrade
    sudo apt -yqq install $COMMON_PKGS
    sudo apt install build-essential zlib1g-dev libncurses5-dev \
      libgdbm-dev libnss3-dev libssl-dev libreadline-dev libffi-dev \
      libsqlite3-dev wget libbz2-dev
    wget https://www.python.org/ftp/python/3.8.9/Python-3.8.9.tgz
    tar -xf Python-3.8.9.tgz
    cd Python-3.8.9
    ./configure --enable-optimizations
    make -j 8
    sudo make install
    update-alternatives --install /usr/bin/python python /usr/bin/python3.8 1
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.8 1
    cd ..
    rm Python-3.8.9.tgz
    curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
    python3 get-pip.py

    # Install Maven
    wget -O $HOME/maven.zip "https://dlcdn.apache.org/maven/maven-3/3.9.2/binaries/apache-maven-3.9.2-bin.zip"
    unzip $HOME/maven.zip -d $HOME
    echo "export PATH=\"\$PATH:$HOME/apache-maven-3.9.2/bin\"" >> $HOME/.bash_profile
}

install_sdkman() {
    sudo apt -yqq install $SDKMAN_DEPS
    curl -s https://get.sdkman.io | /bin/bash
    chmod a+x "$HOME/.sdkman/bin/sdkman-init.sh"
    source "$HOME/.sdkman/bin/sdkman-init.sh"
    mkdir -p $HOME/.sdkman/etc/
    echo "sdkman_auto_answer=true" >> $HOME/.sdkman/etc/config
    echo "SDKMAN_DIR=\"$HOME/.sdkman\"" >> $HOME/.bash_profile
    echo "source \"$HOME/.sdkman/bin/sdkman-init.sh\"" >> $HOME/.bash_profile
}

install_deps() {
    update_and_install_common_pks
    install_sdkman
    echo "source $HOME/.bash_profile >> $HOME/.bashrc"
}

install_java_dep() {
    sdk install java 8.0.265-open
}

install_groovy() {
    install_java_dep
    sdk install groovy 4.0.0-alpha-2
    echo "PATH=\"\$PATH:$HOME/.sdkman/candidates/kotlin/current/bin/\"" >> $HOME/.bash_profile
}

install_java() {
    sdk install java 18.ea.2-open
    echo "PATH=\"\$PATH:$HOME/.sdkman/candidates/java/current/bin/\"" >> $HOME/.bash_profile
}

install_kotlin_from_source() {
    sdk install java 9.0.4-open
    sdk install java 8.0.265-open
    sdk install gradle
    echo "JAVA_HOME=$HOME/.sdkman/candidates/java/8.0.265-open/" >> $HOME/.bash_profile
    echo "JDK_16=$HOME/.sdkman/candidates/java/8.0.265-open/" >> $HOME/.bash_profile
    echo "JDK_17=$HOME/.sdkman/candidates/java/8.0.265-open/" >> $HOME/.bash_profile
    echo "JDK_18=$HOME/.sdkman/candidates/java/8.0.265-open/" >> $HOME/.bash_profile
    echo "JDK_9=$HOME/.sdkman/candidates/java/9.0.4-open/" >> $HOME/.bash_profile
    source $HOME/.bash_profile
    git clone https://github.com/JetBrains/kotlin.git
    cd kotlin
    ./gradlew -Dhttp.socketTimeout=60000 -Dhttp.connectionTimeout=60000 dist
    echo "PATH=\"\$PATH:$HOME/kotlin/dist/kotlinc/bin\"" >> $HOME/.bash_profile
    echo "KOTLIN_INSTALLATION=$HOME/kotlin" >> $HOME/.bash_profile
    cd ..
    source $HOME/.bash_profile
}

install_groovy_from_source() {
    git clone https://github.com/apache/groovy
    sdk install gradle
    sdk install java 11.0.10-open
    cd groovy
    gradle -p bootstrap
    ./gradlew --write-verification-metadata pgp,sha512 --dry-run
    ./gradlew clean dist --continue
    echo "#!/bin/bash" >> $HOME/bin/groovyc
    echo "java -cp $HOME/groovy/build/libs/groovy-5.0.0-SNAPSHOT.jar org.codehaus.groovy.tools.FileSystemCompiler $@" >> $HOME/bin/groovyc
    chmod +x $HOME/bin/groovyc
    echo "PATH=$HOME/bin/:$PATH" >> .bash_profile
    echo "GROOVY_INSTALLATION=$HOME/groovy" >> $HOME/.bash_profile
    cd ..
    source $HOME/.bash_profile
}

install_java_from_source() {
    sdk install java 16.0.1-open
    apt -yqq install build-essential autoconf zip libxss-dev libxxf86vm-dev \
        libxkbfile-dev libxv-dev libx11-dev libxext-dev libxrender-dev \
        libxrandr-dev libxtst-dev libxt-dev libcups2 libcups2-dev \
        libfontconfig-dev libasound2-dev
    apt -yqq install python3.9-distutils
    apt remove python3-apt && apt autoremove && apt autoclean
    apt install python3-apt software-properties-common -yqq
    # TODO we need gcc 10

    git clone https://github.com/openjdk/jdk.git
    cd jdk
    bash configure
    make java.Compiler
}

install_kotlin() {
    install_java_dep
    sdk install kotlin
    echo "PATH=\"\$PATH:$HOME/.sdkman/candidates/kotlin/current/bin/\"" >> $HOME/.bash_profile
}

install_scala() {
    install_java_dep
    sdk install scala
    echo "PATH=\"\$PATH:$HOME/.sdkman/candidates/scala/current/bin/\"" >> $HOME/.bash_profile
}

install_kotlin_all() {
    install_java_dep
    sdk install kotlin 1.4.21  && \
    sdk install kotlin 1.4.20  && \
    sdk install kotlin 1.4.10  && \
    sdk install kotlin 1.4.0   && \
    sdk install kotlin 1.3.72  && \
    sdk install kotlin 1.3.71  && \
    sdk install kotlin 1.3.70  && \
    sdk install kotlin 1.3.61  && \
    sdk install kotlin 1.3.60  && \
    sdk install kotlin 1.3.50  && \
    sdk install kotlin 1.3.41  && \
    sdk install kotlin 1.3.40  && \
    sdk install kotlin 1.3.31  && \
    sdk install kotlin 1.3.30  && \
    sdk install kotlin 1.3.21  && \
    sdk install kotlin 1.3.20  && \
    sdk install kotlin 1.3.11  && \
    sdk install kotlin 1.3.10  && \
    sdk install kotlin 1.3.0   && \
    sdk install kotlin 1.2.71  && \
    sdk install kotlin 1.2.70  && \
    sdk install kotlin 1.2.61  && \
    sdk install kotlin 1.2.60  && \
    sdk install kotlin 1.2.51  && \
    sdk install kotlin 1.2.50  && \
    sdk install kotlin 1.2.41  && \
    sdk install kotlin 1.2.40  && \
    sdk install kotlin 1.2.31  && \
    sdk install kotlin 1.2.30  && \
    sdk install kotlin 1.2.21  && \
    sdk install kotlin 1.2.20  && \
    sdk install kotlin 1.2.10  && \
    sdk install kotlin 1.2.0   && \
    sdk install kotlin 1.1.61  && \
    sdk install kotlin 1.1.60  && \
    sdk install kotlin 1.1.51  && \
    sdk install kotlin 1.1.50  && \
    sdk install kotlin 1.1.4-3 && \
    sdk install kotlin 1.1.4-2 && \
    sdk install kotlin 1.1.4   && \
    sdk install kotlin 1.1.3-2 && \
    sdk install kotlin 1.1.3   && \
    sdk install kotlin 1.1.2-5 && \
    sdk install kotlin 1.1.2-2 && \
    sdk install kotlin 1.1.2   && \
    sdk install kotlin 1.1.1   && \
    sdk install kotlin 1.1     && \
    sdk install kotlin 1.0.7   && \
    sdk install kotlin 1.0.6   && \
    sdk install kotlin 1.0.5-2 && \
    sdk install kotlin 1.0.5   && \
    sdk install kotlin 1.0.4   && \
    sdk install kotlin 1.0.3   && \
    sdk install kotlin 1.0.2   && \
    sdk install kotlin 1.0.1-2 && \
    sdk install kotlin 1.0.1-1 && \
    sdk install kotlin 1.0.1   && \
    sdk install kotlin 1.0.0
    echo "PATH=\"\$PATH:$HOME/.sdkman/candidates/kotlin/current/bin/\"" >> $HOME/.bash_profile
}

install_check_type_systems() {
    git clone git@github.com:theosotr/api-hephaestus.git
    cd api-hephaestus
    git fetch && git pull
    git checkout stable
    git pull origin stable
    pip3 install -r requirements.txt
    echo "CHECK_TYPE_SYSTEMS=$(pwd)" >> $HOME/.bash_profile
    cd ..
}

add_run_script_to_path() {
    mkdir -p bin
    cp run.sh bin
    echo "PATH=\"\$PATH:$HOME/bin\"" >> $HOME/.bash_profile
}

if [ $# -eq 0 ]
then
        echo "Missing options!"
        echo "(run $0 -h for help)"
        echo ""
        exit 0
fi


while getopts "hskagSjJd" OPTION; do
        case $OPTION in
                d)
                        install_deps
                        install_scala
                        install_check_type_systems
                        add_run_script_to_path
                        ;;

                k)
                        install_deps
                        install_kotlin
                        install_check_type_systems
                        add_run_script_to_path
                        ;;

                s)
                        install_deps
                        install_kotlin_from_source
                        install_check_type_systems
                        add_run_script_to_path
                        ;;

                a)
                        install_deps
                        install_kotlin_all
                        install_check_type_systems
                        add_run_script_to_path
                        ;;

                g)
                        install_deps
                        install_groovy
                        install_check_type_systems
                        add_run_script_to_path
                        ;;

                S)
                        install_deps
                        install_groovy_from_source
                        install_check_type_systems
                        add_run_script_to_path
                        ;;

                j)
                        install_deps
                        install_java
                        install_check_type_systems
                        add_run_script_to_path
                        ;;

                J)
                        install_deps
                        install_java_from_source
                        install_check_type_systems
                        add_run_script_to_path
                        ;;

                h)
                        echo "Usage:"
                        echo "setup.sh -d "
                        echo "setup.sh -k "
                        echo "setup.sh -s "
                        echo "setup.sh -a "
                        echo "setup.sh -g "
                        echo "setup.sh -S "
                        echo ""
                        echo "   -d     Install latest Scala version"
                        echo "   -k     Install latest kotlin version"
                        echo "   -s     Install kotlin from source"
                        echo "   -a     Install all kotlin versions"
                        echo "   -g     Install latest groovy version"
                        echo "   -S     Install groovy from source"
                        echo "   -j     Install latest Java version"
                        echo "   -J     Install Java from source"
                        echo "   -h     help (this output)"
                        exit 0
                        ;;

        esac
done
