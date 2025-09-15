<script lang="ts">
	import { badgeVariants, type Variant } from ".";
	import { cn } from "$lib/utils";

	let className: string | undefined | null = undefined;
	export { className as class };
	export let variant: Variant = "default";
</script>

<div class={cn(badgeVariants({ variant, class: className }))} {...$$restProps}>
	<slot />
</div>
