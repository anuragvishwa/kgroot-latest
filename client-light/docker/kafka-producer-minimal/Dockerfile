# Multi-stage build to create a minimal Kafka console producer image
# Final image size: ~50-80MB (vs 500-700MB for full Kafka)

FROM confluentinc/cp-kafka:7.5.0 AS kafka-source

# Stage 2: Create minimal runtime image
FROM amazoncorretto:17-alpine

# Install required runtime dependencies
RUN apk add --no-cache bash coreutils

# Copy only the necessary Kafka binaries and libraries
COPY --from=kafka-source /usr/bin/kafka-console-producer /usr/bin/
COPY --from=kafka-source /usr/bin/kafka-run-class /usr/bin/
COPY --from=kafka-source /etc/kafka /etc/kafka
COPY --from=kafka-source /usr/share/java/kafka /usr/share/java/kafka
COPY --from=kafka-source /usr/share/java/cp-base-new /usr/share/java/cp-base-new

# Set environment variables
ENV KAFKA_HOME=/usr/share/java/kafka
ENV PATH="${PATH}:/usr/bin"

# Create a non-root user
RUN addgroup -S kafka && adduser -S kafka -G kafka
USER kafka

WORKDIR /home/kafka

# Default command
CMD ["/bin/bash"]
