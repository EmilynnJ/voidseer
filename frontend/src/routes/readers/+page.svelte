<script lang="ts">
  import { page } from '$app/stores';
  import { enhance } from '$app/forms';
  import { error } from '@sveltejs/kit';
  import ReaderCard from '$lib/components/ReaderCard.svelte';
  import Filters from '$lib/components/Filters.svelte';
  import Pagination from '$lib/components/Pagination.svelte';
  import { Button } from '$lib/components/ui/button';
  import { Alert, AlertDescription, AlertTitle } from '$lib/components/ui/alert';
  import { AlertCircle, RefreshCw } from 'lucide-svelte';

  export let data;
  
  // Ensure data is properly typed
  $: ({ readers = [], meta = {}, filters = {}, filterOptions = {} } = data || {});
  $: ({ total = 0, page: currentPage = 1, perPage = 20 } = meta);
  
  // Handle error state
  $: hasError = data?.error;
  $: isLoading = false; // Will be used with form actions
  
  // Calculate total pages for pagination
  $: totalPages = Math.ceil(total / perPage);
  
  // Function to update URL with new filters
  function updateFilters(newFilters) {
    const searchParams = new URLSearchParams();
    
    // Only include non-default values in URL
    if (newFilters.search) searchParams.set('q', newFilters.search);
    if (newFilters.specialties?.length) searchParams.set('specialties', newFilters.specialties.join(','));
    if (newFilters.minRate > 0) searchParams.set('minRate', newFilters.minRate.toString());
    if (newFilters.maxRate < 100) searchParams.set('maxRate', newFilters.maxRate.toString());
    if (newFilters.availableNow) searchParams.set('availableNow', 'true');
    if (newFilters.page > 1) searchParams.set('page', newFilters.page.toString());
    
    // Update URL without page reload (handled by SvelteKit)
    window.history.pushState({}, '', `?${searchParams.toString()}`);
    
    // Trigger data reload
    window.dispatchEvent(new Event('popstate'));
  }
  
  // Handle filter form submission
  function handleFilterSubmit(event) {
    event.preventDefault();
    const formData = new FormData(event.target);
    const newFilters = {
      search: formData.get('search')?.toString() || '',
      specialties: formData.getAll('specialties').map(s => s.toString()),
      minRate: parseFloat(formData.get('minRate')?.toString() || '0'),
      maxRate: parseFloat(formData.get('maxRate')?.toString() || '100'),
      availableNow: formData.get('availableNow') === 'on',
      page: 1 // Reset to first page on new filter
    };
    updateFilters(newFilters);
  }
  
  // Handle pagination
  function goToPage(page: number) {
    updateFilters({ ...filters, page });
  }
  
  // Handle retry on error
  function retry() {
    window.location.reload();
  }
</script>

<svelte:head>
  <title>Find a Reader - SoulSeer</title>
  <meta name="description" content="Browse our community of gifted and authentic psychic readers. Filter by specialty, availability, and more to find the perfect match for you." />
</svelte:head>

<div class="container mx-auto px-4 py-8">
  <div class="text-center mb-8">
    <h1 class="text-4xl font-bold text-primary">Find Your Reader</h1>
    <p class="mt-2 text-lg text-muted-foreground">Search and filter our entire community of trusted advisors.</p>
  </div>

  {#if hasError}
    <div class="max-w-2xl mx-auto">
      <Alert variant="destructive">
        <AlertCircle class="h-4 w-4" />
        <AlertTitle>Error Loading Readers</AlertTitle>
        <AlertDescription>
          {hasError.message || 'An unexpected error occurred while loading readers.'}
        </AlertDescription>
        <div class="mt-4">
          <Button variant="outline" on:click={retry}>
            <RefreshCw class="mr-2 h-4 w-4" />
            Retry
          </Button>
        </div>
      </Alert>
    </div>
  {:else}
    <form method="GET" on:submit|preventDefault={handleFilterSubmit} class="grid grid-cols-1 lg:grid-cols-4 gap-8">
      <div class="lg:col-span-1">
        <Filters 
          {filterOptions} 
          initialFilters={filters} 
        />
      </div>
      
      <div class="lg:col-span-3">
        {#if readers && readers.length > 0}
          <div class="mb-6">
            <p class="text-sm text-muted-foreground">
              Showing {Math.min((currentPage - 1) * perPage + 1, total)}-{Math.min(currentPage * perPage, total)} of {total} readers
            </p>
          </div>
          
          <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-6">
            {#each readers as reader (reader.id)}
              <ReaderCard {reader} />
            {/each}
          </div>
          
          {#if totalPages > 1}
            <div class="mt-8">
              <Pagination 
                currentPage={currentPage} 
                totalPages={totalPages} 
                onPageChange={goToPage} 
              />
            </div>
          {/if}
          
        {:else}
          <div class="text-center py-16 border rounded-lg bg-card">
            <h3 class="text-xl font-semibold">No Readers Found</h3>
            <p class="text-muted-foreground mt-2">
              {filters.search || filters.specialties?.length || filters.minRate > 0 || filters.maxRate < 100 || filters.availableNow
                ? 'Try adjusting your filters or check back later.'
                : 'No readers are currently available. Please check back later.'
              }
            </p>
          </div>
        {/if}
      </div>
    </form>
  {/if}
</div>
