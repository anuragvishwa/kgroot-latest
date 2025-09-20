# Build
FROM golang:1.22-alpine AS build
WORKDIR /src

# tools needed for module downloads
RUN apk add --no-cache git

# copy only go.mod (go.sum may not exist yet)
COPY go.mod ./
RUN go mod download

# now copy the rest and write missing sums
COPY . .
RUN go mod tidy

# build static binary
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
    go build -trimpath -ldflags="-s -w" -o /out/state-watcher main.go

# Run
FROM gcr.io/distroless/static:nonroot
WORKDIR /
COPY --from=build /out/state-watcher /state-watcher
USER 65532:65532
ENTRYPOINT ["/state-watcher"]
