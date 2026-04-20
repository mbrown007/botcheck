---
title: "Advanced Prompt Engineering Patterns in GenAIScript: Few-Shot Learning
  and Dynamic Composition"
date: 2025-05-27
authors: genaiscript
draft: true
tags:
  - genaiscript
  - advanced
  - prompt-engineering
  - few-shot
  - dynamic
  - chaining

---

## Introduction

When you’re ready to move beyond basic prompt templates in GenAIScript, advanced techniques like few-shot learning, dynamic prompt composition, and prompt chaining can supercharge your scripts. This article will walk you through real script patterns, line by line 🧑‍💻—showing you how to craft more intelligent, context-aware, and flexible prompts.

---

## Few-Shot Learning: Giving the Model Examples

Few-shot learning lets you anchor the model's behavior with clear examples. This increases control and reduces ambiguity in its responses.

```js
// Provide multiple examples to guide the model
const examples = [
  { input: "Translate 'hello' to French", output: "bonjour" },
  { input: "Translate 'goodbye' to French", output: "au revoir" },
  { input: "Translate 'cat' to French", output: "chat" }
]
```

- Here, `examples` is an array of objects, each with an `input` and corresponding `output`. These act as guiding demonstrations for the model.

```js
def("EXAMPLES", examples.map(e => `Input: ${e.input}\nOutput: ${e.output}`).join("\n---\n"))
```

- `def` sets a variable called `EXAMPLES`. It concatenates all example pairs, separated by '---', formatting each one for clarity.

```js
def("PROMPT_INPUT", "Translate 'dog' to French")
```
- This defines another variable for the specific example you want to generate.

```js
$`
You are a translation expert. Use the following examples to guide your answer.

{EXAMPLES}

Now, {PROMPT_INPUT}
`.role("system")
```

- This uses a [template string prompt](https://microsoft.github.io/genaiscript/docs/prompting/) with the system role, incorporating your built examples and current input. The model will now see the pattern you expect.

```js
const fewShotResult = await $`
Input: {PROMPT_INPUT}
Output:
`.options({ temperature: 0.2 })
```

- This prompt requests the output for your new input, using a low temperature for consistency. The result will be assigned to `fewShotResult`.

---

## Dynamic Prompt Composition: Personalizing with Context

GenAIScript lets you build prompts dynamically—so you can tailor tasks to the user, the data, or any variable you like.

```js
function buildDynamicPrompt(userProfile) {
  let prompt = `You are a personalized assistant.`
  if (userProfile.industry) {
    prompt += `\nYou work in the ${userProfile.industry} industry.`
  }
  if (userProfile.goal) {
    prompt += `\nYour main goal is: ${userProfile.goal}`
  }
  return prompt
}
```
- This function constructs a prompt string based on a user's profile. Information like `industry` and `goal` are conditionally included, making the prompt context-rich.

```js
const userProfile = {
  name: "Jane",
  industry: "Healthcare",
  goal: "Optimize patient scheduling"
}
```

- `userProfile` is an example data object you might get from user input or a database.

```js
def("DYNAMIC_SYSTEM_PROMPT", buildDynamicPrompt(userProfile))
```

- Store the composed prompt into `DYNAMIC_SYSTEM_PROMPT`, ready for injection into a template.

```js
$`{DYNAMIC_SYSTEM_PROMPT}`.role("system")
```
- Send the dynamic prompt as a system message to set the context for the model.

```js
const dynamicResult = await $`
Given the user's goal, suggest three actionable strategies tailored to their industry.
`.options({ temperature: 0.3 })
```
- Now, in the context set above, you ask the model for industry-relevant strategies.

---

## Prompt Chaining: Building Complex Workflows

For multi-stage reasoning, chain outputs from one step into the next prompt.

```js
const summary = await $`
Summarize the following user objective in one sentence:
{userProfile.goal}
`.options({ temperature: 0.1 })

def("OBJECTIVE_SUMMARY", summary.text)
```
- Here, you ask the model to summarize the user's goal, then store this summary for reuse.

```js
const brainstorm = await $`
Brainstorm five innovative solutions for this objective:
{OBJECTIVE_SUMMARY}
`.options({ temperature: 0.6 })
```
- Use the summary as a jumping-off point for brainstorming solutions, letting each prompt build on the last for richer results.

---

## Putting It All Together: Full Script Output

For automated runs, you might log each result:

```js
console.log("Few-shot result:", fewShotResult.text)
console.log("Dynamic prompt result:", dynamicResult.text)
console.log("Chained brainstorm:", brainstorm.text)
```
- These lines print out the results of each advanced pattern, so you can inspect or forward responses.

---

## Conclusion

By incorporating few-shot examples, dynamic templates, and prompt chaining, GenAIScript scripts become more than simple input-output tools—they become adaptable, context-sensitive systems ready for real-world tasks.

Check out more advanced examples in [the GenAIScript sample collection](https://github.com/microsoft/genaiscript/tree/main/packages/sample/src).

Happy scripting! 🚀