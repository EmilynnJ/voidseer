<script lang="ts">
  import { page } from '$app/stores';
  import { Button } from '$lib/components/ui/button';
  import { Alert, AlertDescription, AlertTitle } from '$lib/components/ui/alert';
  import { AlertCircle, Home, RefreshCw } from 'lucide-svelte';

  // Get the error from the page store
  $: error = $page.error;
  $: status = error?.status || 500;
  $: message = error?.message || 'An unexpected error occurred';
  $: stack = error?.stack;

  // Define error messages for common status codes
  const errorMessages = {
    400: 'Bad Request',
    401: 'Unauthorized',
    403: 'Forbidden',
    404: 'Page Not Found',
    405: 'Method Not Allowed',
    408: 'Request Timeout',
    409: 'Conflict',
    422: 'Unprocessable Entity',
    429: 'Too Many Requests',
    500: 'Internal Server Error',
    502: 'Bad Gateway',
    503: 'Service Unavailable',
    504: 'Gateway Timeout'
  };

  // Get the error title based on status code
  $: title = errorMessages[status] || 'Something went wrong';

  // Function to handle retry
  function retry() {
    window.location.reload();
  }

  // Function to go to home page
  function goHome() {
    window.location.href = '/';
  }
</script>

<div class="min-h-screen flex items-center justify-center bg-background p-4">
  <div class="w-full max-w-2xl">
    <div class="text-center mb-8">
      <h1 class="text-6xl font-bold text-primary mb-2">{status}</h1>
      <h2 class="text-2xl font-semibold text-foreground mb-4">{title}</h2>
      <p class="text-muted-foreground">{message}</p>
    </div>

    <div class="bg-card rounded-lg border overflow-hidden">
      <div class="p-6">
        <Alert variant={status >= 500 ? 'destructive' : 'default'}" class="mb-6">
          <AlertCircle class="h-5 w-5" />
          <AlertTitle class="text-lg">{title}</AlertTitle>
          <AlertDescription class="mt-2">
            <p class="mb-4">{message}</p>
            
            {#if stack}
              <details class="mb-4">
                <summary class="text-sm cursor-pointer text-muted-foreground">
                  Show technical details
                </summary>
                <pre class="mt-2 p-3 bg-muted/50 rounded overflow-auto text-xs font-mono">
                  {stack}
                </pre>
              </details>
            {/if}

            <div class="flex flex-col sm:flex-row gap-3 mt-6">
              <Button on:click={retry} class="flex-1 sm:flex-none">
                <RefreshCw class="mr-2 h-4 w-4" />
                Try Again
              </Button>
              <Button variant="outline" on:click={goHome} class="flex-1 sm:flex-none">
                <Home class="mr-2 h-4 w-4" />
                Go to Homepage
              </Button>
            </div>
          </AlertDescription>
        </Alert>

        <div class="mt-8 pt-6 border-t border-border">
          <h3 class="text-sm font-medium text-muted-foreground mb-3">Need help?</h3>
          <p class="text-sm text-muted-foreground mb-4">
            If you continue to experience issues, please contact our support team.
          </p>
          <div class="flex gap-3">
            <Button variant="outline" size="sm" on:click={() => window.location.href = '/contact'}>Contact Support</Button>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
