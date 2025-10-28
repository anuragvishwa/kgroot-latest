# GPT-5 Integration Guide

## Overview

The KGroot RCA system now supports **GPT-5**, OpenAI's latest reasoning model with enhanced capabilities for complex technical analysis.

## GPT-5 vs GPT-4o

| Feature | GPT-5 | GPT-4o |
|---------|-------|--------|
| **API** | Responses API | Chat Completions API |
| **Reasoning** | Deep chain-of-thought | Standard generation |
| **Control** | reasoning_effort, verbosity | temperature, top_p |
| **Speed** | Configurable (minimal to high) | Fixed |
| **Accuracy** | Higher for complex tasks | Good general purpose |
| **Cost** | More expensive, but configurable | Lower, fixed |

## Configuration

### 1. Install Latest OpenAI Package

```bash
pip install --upgrade "openai>=1.60.0"
```

### 2. Configure in config.yaml

```yaml
openai:
  api_key: "sk-your-api-key-here"
  embedding_model: "text-embedding-3-small"

  # Model Selection
  chat_model: "gpt-5"  # or "gpt-5-mini", "gpt-5-nano", "gpt-4o"

  # GPT-5 Specific Settings
  reasoning_effort: "medium"  # minimal, low, medium, high
  verbosity: "medium"         # low, medium, high

  enable_llm_analysis: true
```

## Model Selection

### GPT-5 (Full Model)
- **Best for**: Complex root cause analysis, multi-step reasoning
- **reasoning_effort**:
  - `minimal`: Fastest, good for simple failures (~100ms reasoning)
  - `low`: Balanced speed/quality (~500ms reasoning)
  - `medium`: Default, good for most cases (~2s reasoning)
  - `high`: Best accuracy for complex failures (~5-10s reasoning)
- **verbosity**:
  - `low`: Concise output (~200 tokens)
  - `medium`: Standard output (~500 tokens)
  - `high`: Detailed explanations (~1000+ tokens)

**Example Cost**: ~$0.05-0.15 per RCA analysis (depending on effort/verbosity)

### GPT-5-Mini
- **Best for**: Fast, cost-effective analysis
- **Use when**: Budget-conscious, simpler failures
- **Cost**: ~$0.01-0.03 per analysis

### GPT-5-Nano
- **Best for**: High-throughput, simple classification
- **Use when**: Need to analyze many failures quickly
- **Cost**: ~$0.001-0.005 per analysis

### GPT-4o (Fallback)
- **Best for**: When GPT-5 is unavailable or for general use
- **Cost**: ~$0.01-0.02 per analysis
- **Note**: Uses standard Chat Completions API

## Usage Examples

### Using GPT-5 with High Reasoning

```python
orchestrator = RCAOrchestrator(
    openai_api_key=api_key,
    enable_llm=True,
    llm_model="gpt-5",
    reasoning_effort="high",  # Deep analysis
    verbosity="high"          # Detailed explanations
)
```

### Fast Analysis with Minimal Reasoning

```python
orchestrator = RCAOrchestrator(
    openai_api_key=api_key,
    enable_llm=True,
    llm_model="gpt-5",
    reasoning_effort="minimal",  # Quick response
    verbosity="low"              # Concise output
)
```

### Cost-Optimized with GPT-5-Mini

```python
orchestrator = RCAOrchestrator(
    openai_api_key=api_key,
    enable_llm=True,
    llm_model="gpt-5-mini",
    reasoning_effort="medium",
    verbosity="medium"
)
```

### Fallback to GPT-4o

```python
orchestrator = RCAOrchestrator(
    openai_api_key=api_key,
    enable_llm=True,
    llm_model="gpt-4o",  # Uses Chat Completions API
    # reasoning_effort and verbosity are ignored
)
```

## API Differences

### GPT-5 (Responses API)

```python
# Used internally when model starts with "gpt-5"
response = client.responses.create(
    model="gpt-5",
    input=prompt,
    reasoning={"effort": "medium"},
    text={"verbosity": "medium"},
    developer_message={
        "role": "developer",
        "content": "System instructions..."
    }
)

output = response.output_text
```

### GPT-4o (Chat Completions API)

```python
# Used internally when model is "gpt-4o"
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "System instructions..."},
        {"role": "user", "content": prompt}
    ],
    temperature=0.1,
    response_format={"type": "json_object"}
)

output = response.choices[0].message.content
```

## Performance Comparison

| Configuration | Analysis Time | Accuracy | Cost | Best For |
|--------------|---------------|----------|------|----------|
| GPT-5 (high) | ~5-10s | Highest | $$$ | Critical incidents |
| GPT-5 (medium) | ~2-3s | Very high | $$ | Standard RCA |
| GPT-5 (low) | ~1s | High | $ | Quick analysis |
| GPT-5 (minimal) | ~500ms | Good | $ | Simple failures |
| GPT-5-mini (medium) | ~1-2s | High | $ | Cost-optimized |
| GPT-5-nano (low) | ~500ms | Good | ¢ | High-throughput |
| GPT-4o | ~2s | Good | $ | General purpose |
| Rule-based (no LLM) | <500ms | Medium | Free | Offline/budget |

## When to Use Each Model

### GPT-5 (Full) + High Reasoning
✅ Critical production incidents
✅ Complex multi-service failures
✅ When accuracy is paramount
✅ Post-mortem analysis

### GPT-5 + Medium Reasoning (Default)
✅ Standard RCA workflows
✅ Most Kubernetes failures
✅ Balance of speed and accuracy
✅ Real-time incident response

### GPT-5 + Minimal/Low Reasoning
✅ Simple resource exhaustion
✅ Known failure patterns
✅ Quick preliminary analysis
✅ High-frequency monitoring

### GPT-5-Mini
✅ Development environments
✅ Cost-sensitive deployments
✅ Medium complexity failures
✅ High volume analysis

### GPT-5-Nano
✅ Alert classification
✅ Pattern recognition
✅ Batch processing
✅ Thousands of analyses per day

### GPT-4o
✅ GPT-5 unavailable
✅ Legacy workflows
✅ Standard failures
✅ When reasoning not needed

## Cost Optimization Tips

1. **Start with Medium Reasoning**: Good balance for most cases
2. **Use Minimal for Simple Cases**: Check if pattern matches first, only deep-dive if needed
3. **Batch Similar Failures**: Use rule-based matching first, LLM for unclear cases
4. **Cache Common Patterns**: Store LLM responses for recurring failures
5. **Progressive Enhancement**: Start minimal, increase effort if confidence is low

## Example Workflow

```python
async def smart_rca(fault_id, events):
    # Quick pattern match first (free)
    matched_patterns = matcher.find_similar_patterns(fpg, patterns, top_k=3)

    if matched_patterns[0].similarity_score > 0.9:
        # High confidence match - use minimal reasoning
        orchestrator = RCAOrchestrator(
            llm_model="gpt-5",
            reasoning_effort="minimal",
            verbosity="low"
        )
    else:
        # Unclear case - use medium reasoning
        orchestrator = RCAOrchestrator(
            llm_model="gpt-5",
            reasoning_effort="medium",
            verbosity="medium"
        )

    result = await orchestrator.analyze_failure(fault_id, events)
    return result
```

## Migration from GPT-4o

If you're currently using GPT-4o:

```yaml
# Old config
openai:
  chat_model: "gpt-4o"

# New config (equivalent performance, more control)
openai:
  chat_model: "gpt-5"
  reasoning_effort: "minimal"  # Similar to GPT-4o
  verbosity: "medium"
```

For better accuracy:

```yaml
openai:
  chat_model: "gpt-5"
  reasoning_effort: "medium"  # Better than GPT-4o
  verbosity: "medium"
```

## Troubleshooting

### "Model not found" error
- Make sure you have access to GPT-5 beta
- Update OpenAI package: `pip install --upgrade openai`
- Check API key has GPT-5 access

### High costs
- Reduce reasoning_effort from "high" to "medium" or "low"
- Reduce verbosity from "high" to "medium" or "low"
- Use GPT-5-mini instead of GPT-5
- Use rule-based mode first, LLM only when needed

### Slow responses
- Use reasoning_effort="minimal" or "low"
- Use verbosity="low"
- Consider GPT-5-nano for speed
- Or fall back to GPT-4o

### JSON parsing errors
- GPT-5 may return text instead of JSON
- The code handles this automatically
- Wrapped in: `{"root_cause_diagnosis": text, "raw_output": true}`

## Support

- **OpenAI GPT-5 Docs**: https://platform.openai.com/docs/models/gpt-5
- **Responses API**: https://platform.openai.com/docs/api-reference/responses
- **Pricing**: https://openai.com/pricing

---

**Summary**: GPT-5 provides more control and better reasoning for complex RCA. Start with medium reasoning, adjust based on your needs and budget.
