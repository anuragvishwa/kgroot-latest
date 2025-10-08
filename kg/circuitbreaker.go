package main

import (
	"context"
	"errors"
	"sync"
	"time"
)

// CircuitBreaker implements the circuit breaker pattern for Neo4j operations
// This prevents cascading failures when Neo4j is unavailable

type CircuitState int

const (
	StateClosed CircuitState = iota // Normal operation
	StateOpen                        // Failing, rejecting requests
	StateHalfOpen                    // Testing if service recovered
)

type CircuitBreaker struct {
	mu sync.RWMutex

	// Configuration
	maxFailures     int
	resetTimeout    time.Duration
	halfOpenTimeout time.Duration

	// State
	state        CircuitState
	failures     int
	lastFailTime time.Time
	lastAttempt  time.Time
}

var (
	ErrCircuitOpen     = errors.New("circuit breaker is open")
	ErrTooManyRequests = errors.New("too many requests in half-open state")
)

func NewCircuitBreaker(maxFailures int, resetTimeout time.Duration) *CircuitBreaker {
	return &CircuitBreaker{
		maxFailures:     maxFailures,
		resetTimeout:    resetTimeout,
		halfOpenTimeout: 10 * time.Second,
		state:           StateClosed,
	}
}

// Execute runs the operation through the circuit breaker
func (cb *CircuitBreaker) Execute(ctx context.Context, fn func(context.Context) error) error {
	// Check if we can execute
	if err := cb.beforeRequest(); err != nil {
		return err
	}

	// Execute the operation
	err := fn(ctx)

	// Record the result
	cb.afterRequest(err)

	return err
}

func (cb *CircuitBreaker) beforeRequest() error {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	now := time.Now()

	switch cb.state {
	case StateClosed:
		// Normal operation
		return nil

	case StateOpen:
		// Check if we should transition to half-open
		if now.Sub(cb.lastFailTime) > cb.resetTimeout {
			cb.state = StateHalfOpen
			cb.lastAttempt = now
			return nil
		}
		return ErrCircuitOpen

	case StateHalfOpen:
		// Allow one request to test if service recovered
		if now.Sub(cb.lastAttempt) < cb.halfOpenTimeout {
			return ErrTooManyRequests
		}
		cb.lastAttempt = now
		return nil
	}

	return nil
}

func (cb *CircuitBreaker) afterRequest(err error) {
	cb.mu.Lock()
	defer cb.mu.Unlock()

	if err != nil {
		cb.onFailure()
	} else {
		cb.onSuccess()
	}
}

func (cb *CircuitBreaker) onFailure() {
	cb.failures++
	cb.lastFailTime = time.Now()

	switch cb.state {
	case StateClosed:
		if cb.failures >= cb.maxFailures {
			cb.state = StateOpen
			// Update metrics
			if circuitBreakerState != nil {
				circuitBreakerState.WithLabelValues("neo4j").Set(1) // Open
			}
		}

	case StateHalfOpen:
		// Failed while testing, go back to open
		cb.state = StateOpen
		if circuitBreakerState != nil {
			circuitBreakerState.WithLabelValues("neo4j").Set(1) // Open
		}
	}
}

func (cb *CircuitBreaker) onSuccess() {
	switch cb.state {
	case StateClosed:
		// Reset failure count on success
		cb.failures = 0

	case StateHalfOpen:
		// Recovered! Close the circuit
		cb.state = StateClosed
		cb.failures = 0
		if circuitBreakerState != nil {
			circuitBreakerState.WithLabelValues("neo4j").Set(0) // Closed
		}
	}
}

func (cb *CircuitBreaker) GetState() CircuitState {
	cb.mu.RLock()
	defer cb.mu.RUnlock()
	return cb.state
}

func (cb *CircuitBreaker) GetFailures() int {
	cb.mu.RLock()
	defer cb.mu.RUnlock()
	return cb.failures
}

// HealthCheck returns true if the circuit is closed (healthy)
func (cb *CircuitBreaker) HealthCheck() bool {
	cb.mu.RLock()
	defer cb.mu.RUnlock()
	return cb.state == StateClosed
}
