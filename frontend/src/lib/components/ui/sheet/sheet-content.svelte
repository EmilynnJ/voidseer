<script lang="ts">
	import { Sheet as SheetPrimitive } from "bits-ui";
	import { cn } from "$lib/utils";
	import { tv, type VariantProps } from "tailwind-variants";
	import SheetOverlay from "./sheet-overlay.svelte";
	import SheetPortal from "./sheet-portal.svelte";

	type $$Props = SheetPrimitive.ContentProps & VariantProps<typeof sheetVariants>;
	type $$Events = SheetPrimitive.ContentEvents;

	let className: $$Props["class"] = undefined;
	export let side: $$Props["side"] = "right";
	export { className as class };

	const sheetVariants = tv({
		base: "fixed z-50 gap-4 bg-background p-6 shadow-lg transition ease-in-out data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:duration-300 data-[state=open]:duration-500",
		variants: {
			side: {
				top: "inset-x-0 top-0 border-b data-[state=closed]:slide-out-to-top data-[state=open]:slide-in-from-top",
				bottom:
					"inset-x-0 bottom-0 border-t data-[state=closed]:slide-out-to-bottom data-[state=open]:slide-in-from-bottom",
				left:
					"inset-y-0 left-0 h-full w-3/4 border-r data-[state=closed]:slide-out-to-left data-[state=open]:slide-in-from-left sm:max-w-sm",
				right:
					"inset-y-0 right-0 h-full w-3/4 border-l data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right sm:max-w-sm",
			},
		},
		defaultVariants: {
			side: "right",
		},
	});
</script>

<SheetPortal>
	<SheetOverlay />
	<SheetPrimitive.Content
		class={cn(sheetVariants({ side }), className)}
		{...$$restProps}
		on:let
		on:let
		on:let
		on:let
	>
		<slot />
		<SheetPrimitive.Close
			class="absolute right-4 top-4 rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-secondary"
		>
			<svg
				xmlns="http://www.w3.org/2000/svg"
				width="24"
				height="24"
				viewBox="0 0 24 24"
				fill="none"
				stroke="currentColor"
				stroke-width="2"
				stroke-linecap="round"
				stroke-linejoin="round"
				class="h-4 w-4"
				><path d="M18 6 6 18" /><path d="m6 6 12 12" /></svg
			>
			<span class="sr-only">Close</span>
		</SheetPrimitive.Close>
	</SheetPrimitive.Content>
</SheetPortal>
