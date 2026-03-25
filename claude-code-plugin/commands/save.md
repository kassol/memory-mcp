---
name: save
description: Quick save to long-term memory
arguments: content to save
---

Save the provided content to long-term memory. Analyze the content to determine the appropriate entity_type and entity_key, then run:

```bash
mem remember "<content>" --type <inferred_type> --key <inferred_key>
```

If the content is ambiguous, ask the user for the type and key.
