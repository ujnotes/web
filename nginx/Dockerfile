# syntax=docker/dockerfile:1.4

FROM nginx:latest

ENV CLOSURE_COMPILER_VERSION 20240317

# Create the gclosure directory first
RUN mkdir -p /usr/local/lib/gclosure

# Download and move the Closure Compiler JAR in one step
RUN wget -O /usr/local/lib/gclosure/closure-compiler.jar \
"https://repo1.maven.org/maven2/com/google/javascript/closure-compiler/v$CLOSURE_COMPILER_VERSION/closure-compiler-v$CLOSURE_COMPILER_VERSION.jar"

EXPOSE 80 443

WORKDIR /app