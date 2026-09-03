# AI-assisted mooring-line inspection

## Purpose

The AI inspection module provides visual assistance for mooring-line inspection photographs. It is intentionally separated from engineering acceptance and line-life decisions.

## Workflow

`Photo → AI visual classification → findings/confidence/image-quality → operator confirmation → inspection history`

The AI may classify visible conditions such as:

- abrasion
- glazing / heat damage
- broken yarns or strands
- cuts / severed fibres
- chemical contamination
- deformation / flattening
- sheath / cover damage
- splice / end damage
- unknown condition

If the image is poor or insufficient, the AI can request a new photograph.

## Engineering boundary

The AI does **not**:

- estimate wear percentage;
- estimate residual breaking strength;
- invent MBL, LDBF, WLL or TDBF values;
- determine remaining service life;
- declare a line safe or unsafe for operation;
- recommend replacement or end-for-ending.

Operator confirmation records that the AI observation has been reviewed. It does not automatically modify `line_life_history`.

A future engineering-assessment layer may map confirmed observations to manufacturer, MEG4, class/RO and SMS criteria when those validated criteria are available.

## Configuration

Set the API key only in Streamlit Secrets:

```toml
OPENAI_API_KEY = "..."
```

The key must never be committed to GitHub or placed in application source code.

The current implementation uses the OpenAI Responses API with image input. OpenAI's current documentation describes image inputs through `input_image` and the Responses API. The application uses `gpt-5.6-luna` as the default cost-sensitive vision model and keeps the model name in one constant so it can be changed without altering the inspection workflow.
