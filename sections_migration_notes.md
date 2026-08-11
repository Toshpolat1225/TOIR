# Migration Pattern: Supabase to FastAPI

This document outlines the standard procedure for migrating a frontend page from using the Supabase JS client to our new FastAPI backend via the `lib/api.ts` client.

## 1. Authentication

The `useAuth()` hook from `lib/auth-context.tsx` remains the primary way to access user and authentication state. Its internal implementation has been switched to use the FastAPI backend, but its external API is unchanged. No changes are needed in components that just consume auth state.

## 2. API Client

All new data-fetching logic must use the centralized API client located at `lib/api.ts`.

**DO NOT** use `fetch` or other HTTP clients directly in components.

The client is structured by resource. For example, to access section endpoints:

```typescript
import { api } from '@/lib/api';

const sections = await api.sections.list({ limit: 10, offset: 0 });
const newSection = await api.sections.create({ name: 'New Section' });
```

## 3. CRUD Operation Mapping

The following examples demonstrate the direct replacement pattern for the `sections` page. This pattern should be applied to all other resources.

### List (Read)

**Supabase:**
```typescript
const { data, error } = await supabase
  .from("sections")
  .select("id,name,created_at")
  .order("name", { ascending: true });
```

**FastAPI:**
```typescript
import { api } from '@/lib/api';

const response = await api.sections.list({ limit: 1000, offset: 0, sort_by: 'name', sort_order: 'asc' });
const data = response.items; // Note: the data is nested under `items`
```

### Create

**Supabase:**
```typescript
const { error } = await supabase.from("sections").insert({ name });
```

**FastAPI:**
```typescript
import { api } from '@/lib/api';

await api.sections.create({ name });
```

### Delete

**Supabase:**
```typescript
const { error } = await supabase.from("sections").delete().eq("id", id);
```

**FastAPI:**
```typescript
import { api } from '@/lib/api';

await api.sections.remove(id);
```

## 4. Error Handling

The `api` client will throw an `Error` for non-2xx responses. The error `message` will contain the detail from the FastAPI backend. Use a `try...catch` block to handle API errors and display them to the user.

This approach replaces checking the `error` object returned by Supabase.