# Minimal Kafka Console Producer Image

A lightweight Docker image containing only `kafka-console-producer` for Kafka operations.

## Image Comparison

| Image | Size | Use Case |
|-------|------|----------|
| `confluentinc/cp-kafka:7.5.0` | ~500-700MB | Full Kafka broker + tools |
| `edenhill/kcat:1.7.1` | ~20-30MB | Lightweight Kafka client (kcat/kafkacat) |
| **This image** | ~50-80MB | Official Kafka producer tool only |

## Why This Image?

- **Smaller than full Kafka**: 90% size reduction vs. full Kafka image
- **Official tools**: Uses the official Kafka console producer (not third-party)
- **Fast deployment**: Significantly faster image pull times
- **Secure**: Minimal attack surface with fewer dependencies

## Building the Image

```bash
# Build the image
docker build -t anuragvishwa/kafka-producer-minimal:1.0.0 .

# Test the image locally
docker run --rm anuragvishwa/kafka-producer-minimal:1.0.0 kafka-console-producer --version

# Push to Docker Hub
docker push anuragvishwa/kafka-producer-minimal:1.0.0
```

## Using the Image

### Direct Docker Run

```bash
echo "test-key::test-message" | docker run -i --rm \
  anuragvishwa/kafka-producer-minimal:1.0.0 \
  kafka-console-producer \
    --bootstrap-server your-kafka:9092 \
    --topic test-topic \
    --property "parse.key=true" \
    --property "key.separator=::"
```

### In Kubernetes Job

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: kafka-producer-job
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: producer
        image: anuragvishwa/kafka-producer-minimal:1.0.0
        command:
        - /bin/sh
        - -c
        - |
          echo 'my-key::{"message":"hello"}' | \
          kafka-console-producer \
            --bootstrap-server kafka:9092 \
            --topic my-topic \
            --property "parse.key=true" \
            --property "key.separator=::"
```

## What's Included

- Java 17 JRE (Alpine-based)
- kafka-console-producer binary
- kafka-run-class (required dependency)
- Kafka libraries (/usr/share/java/kafka)
- Confluent Platform base libraries
- Bash and coreutils

## What's NOT Included

- Kafka broker/server
- Zookeeper
- Schema Registry
- Connect framework
- Streams libraries
- KSQL
- Other Kafka CLI tools (kafka-topics, kafka-consumer-perf-test, etc.)

## Security

- Runs as non-root user `kafka`
- Minimal Alpine base image
- Only essential dependencies included
- Regular Java security updates via eclipse-temurin

## Maintenance

Update the Kafka version by changing the source image:

```dockerfile
FROM confluentinc/cp-kafka:7.6.0 AS kafka-source  # Update version here
```

Then rebuild and push with a new tag.
