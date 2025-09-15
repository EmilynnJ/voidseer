<script lang="ts">
	import { cn } from "$lib/utils";

	type $$Props = {
		type?:
			| 'text'
			| 'email'
			| 'password'
			| 'number'
			| 'tel'
			| 'url'
			| 'date'
			| 'time'
			| 'search';
		disabled?: boolean;
		class?: string;
	};

	export let type: $$Props["type"] = "text";
	export let disabled: $$Props["disabled"] = false;
	let className: $$Props["class"] = undefined;
	export { className as class };
</script>

<input
	{type}
	{disabled}
	class={cn(
		"flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
		className
	)}
	{...$$restProps}
/>
