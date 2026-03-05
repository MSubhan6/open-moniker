# Multi-stage build for Java resolver
FROM maven:3.9-eclipse-temurin-21 AS build

WORKDIR /build

# Copy pom.xml and download dependencies (cached layer)
COPY resolver-java/pom.xml ./
RUN mvn dependency:go-offline -B

# Copy source and build
COPY resolver-java/src ./src
RUN mvn clean package -DskipTests -B

# Runtime image
FROM eclipse-temurin:21-jre-jammy

WORKDIR /app

# Copy JAR from build stage
COPY --from=build /build/target/resolver-java-0.1.0.jar ./app.jar

# Copy config files
COPY config.yaml catalog.yaml domains.yaml ./

# Expose port
EXPOSE 8054

# Run with optimized JVM flags
ENTRYPOINT ["java", \
    "-XX:+UseZGC", \
    "-XX:+UseContainerSupport", \
    "-XX:MaxRAMPercentage=75.0", \
    "-Djava.security.egd=file:/dev/./urandom", \
    "-jar", "app.jar"]
