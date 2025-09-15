<script lang="ts">
  import { cn } from "$lib/utils";
  
  export let variant = "default" as 'default' | 'destructive' | 'success' | 'warning' | 'info';
  export let className: string | undefined = undefined;
  
  const variantClasses = {
    default: "border border-border bg-background text-foreground",
    destructive: "border-destructive/50 text-destructive dark:border-destructive [&>svg]:text-destructive",
    success: "border-green-500/50 text-green-700 dark:text-green-400 [&>svg]:text-green-500",
    warning: "border-amber-500/50 text-amber-700 dark:text-amber-400 [&>svg]:text-amber-500",
    info: "border-blue-500/50 text-blue-700 dark:text-blue-400 [&>svg]:text-blue-500"
  };
</script>

<div
  role="alert"
  class={cn(
    "relative w-full rounded-lg border p-4 [&>svg~*]:pl-7 [&>svg+div]:translate-y-[-3px] [&>svg]:absolute [&>svg]:left-4 [&>svg]:top-4 [&>svg]:text-foreground",
    variantClasses[variant],
    className
  )}
  {...$$restProps}
>
  <slot />
</div>
