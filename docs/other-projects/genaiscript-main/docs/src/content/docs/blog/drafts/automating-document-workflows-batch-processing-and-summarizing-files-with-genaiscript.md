---
title: "Automating Document Workflows: Batch Processing and Summarizing Files
  with GenAIScript"
date: 2025-05-26
authors: genaiscript
tags:
  - automation
  - batch-processing
  - document-summarization
  - genaiscript
  - workflows
group: automation
draft: true
description: Automatically discover, batch process, and summarize multiple
  documentation files efficiently using GenAIScript.

---

# "Automating Document Workflows: Batch Processing and Summarizing Files with GenAIScript"

Efficiently processing and summarizing large sets of documentation can be a daunting task. With GenAIScript, you can automate the discovery, batch processing, and summarization of a wide range of documentation files with just a few lines of code! 🚀 In this post, we'll break down a GenAIScript that does exactly that—*explaining every step along the way*.

Let's dive in! 👇

---

## Introduction

Imagine you have a large repository of Markdown or MDX documentation files. You want to process them in small groups (batches), generate concise AI summaries for each file, and then combine the results into an overview. This script shows you how to make that workflow seamless and scalable using GenAIScript’s automation capabilities.

---

## Step-by-Step: How the Script Works

### 1. Script Metadata and Parameters

```typescript
title = "Automating Document Workflows: Batch Processing and Summarizing Files with GenAIScript"
description = "Automatically discover, batch process, and summarize multiple documentation files efficiently using GenAIScript."
group = "automation"
```

- **Purpose & Visibility**: These lines define the script's title, description, and documentation group. This helps organize scripts when they appear in lists or dashboards.

---

```typescript
parameters = {
  fileGlob: {
    type: "string",
    description: "Glob pattern for files to process",
    default: "docs/src/content/docs/**/*.md*"
  },
  batchSize: {
    type: "number",
    description: "Number of files to process in each batch",
    default: 5
  }
}
```

- **Parameters**: The script is configurable!  
  - `fileGlob` specifies which files to process using a glob pattern (e.g., all `.md` and `.mdx` files).
  - `batchSize` determines how many files to process in one go.

---

```typescript
files = fileGlob
accept = ".md,.mdx"
```

- **File Discovery**: These lines tell GenAIScript to only consider files matching the `fileGlob` pattern and extensions `.md` or `.mdx`.

---

## 2. Batch Processing Helper

```typescript
async function* batchFiles(files, batchSize) {
  let batch = []
  for (const file of files) {
    batch.push(file)
    if (batch.length >= batchSize) {
      yield batch
      batch = []
    }
  }
  if (batch.length > 0) yield batch
}
```

- **`batchFiles` Generator**:  
  - This async generator splits an array of files into chunks (batches) of `batchSize`.
  - For each file, it adds it to the current `batch`. When the batch reaches the desired size, it yields that batch and starts a new one.
  - After looping, any remaining files (if not evenly divisible) are yielded as a smaller batch.
  - 💡 Generators like these make working with large datasets *memory-efficient*.

---

## 3. Summarizing Files

```typescript
async function summarizeBatch(batch) {
  const summaries = []
  for (const file of batch) {
    const content = await fs_read_file({ filename: file })
    const summary = await ai("Summarize the following documentation file in 2-3 bullet points:", content)
    summaries.push({ file, summary })
  }
  return summaries
}
```

- **`summarizeBatch`**:  
  - For each file in the batch:
    - `fs_read_file` reads the file content.
    - `ai()` invokes GenAIScript’s AI summarization: the file’s contents are summarized into 2-3 bullet points.
    - The filename and its summary are stored as an object in the `summaries` list.
  - The result: a list of summary objects, one per file in the batch.
  - 📝 This isolates the summarization logic, making it reusable and clear.

---

## 4. Main Workflow

```typescript
async function main({ fileGlob, batchSize }, trace) {
  trace.heading(1, `Batch Processing and Summarization for: ${fileGlob}`)
  const files = (await fs_find_files({ glob: fileGlob, count: 100 })).map(f => f.filename)
  let allSummaries = []
  let batchIndex = 0
  for await (const batch of batchFiles(files, batchSize)) {
    trace.heading(2, `Batch ${++batchIndex}`)
    const summaries = await summarizeBatch(batch)
    allSummaries.push(...summaries)
    for (const { file, summary } of summaries) {
      trace.detailsFenced(file, summary, "markdown")
    }
  }
  trace.heading(1, "Combined Summary")
  for (const { file, summary } of allSummaries) {
    trace.item(`- **${file}**: ${summary}`)
  }
  return allSummaries
}
```

Let's break this down:

- **trace.heading(1, ...)**: Adds a primary heading to the output, indicating which file glob is being processed.
- **fs_find_files**: Finds files matching the glob pattern, limited to 100 by default (adjust as needed).
- **Processing Batches**:
  - Uses `batchFiles` to iterate over files in batches.
  - For each batch:
    - Adds a subheading for clarity.
    - Calls `summarizeBatch` to generate summaries.
    - Displays each file’s summary using `trace.detailsFenced`, nicely formatted in markdown.
  - Summaries from each batch are accumulated in `allSummaries`.
- **Combined View**:
  - After all batches, a final heading and markdown-formatted list of all file summaries is printed.
- **Return Value**: The full summary list is returned for further processing or inspection.

---

## Wrapping Up 🎉

This GenAIScript demonstrates how you can:

- **Automatically discover** relevant files using glob patterns.
- **Batch-process** files to manage resource usage.
- **Generate concise summaries** for documentation using built-in AI integration.
- **Aggregate and format** results for easy review.

If you need to process large documentation sets regularly, customizing this workflow can save countless hours and provide consistent, high-quality overviews of your knowledge base.

Looking for more automation advice and script samples? Check out the [official documentation](https://microsoft.github.io/genaiscript/) or browse community samples in `packages/sample/src/**/*.genai.*js`.

Happy automating! ✨