# ---------- build stage ----------
FROM golang:1.22 AS build
WORKDIR /src

# copy mod files first for better caching
COPY go.mod ./

# download dependencies and generate go.sum
RUN go mod download && go mod tidy

# now copy the actual source
COPY . .

# ensure dependencies are up to date
RUN go mod tidy

# make output dir and build static linux binary
RUN mkdir -p /out
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o /out/graph-builder .

# ---------- runtime stage ----------
FROM gcr.io/distroless/base-debian12
WORKDIR /app
COPY --from=build /out/graph-builder /app/graph-builder
USER nonroot:nonroot
ENTRYPOINT ["/app/graph-builder"]
