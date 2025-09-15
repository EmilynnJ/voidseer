<script lang="ts">
  import { Button } from '$lib/components/ui/button';
  import { ChevronLeft, ChevronRight, MoreHorizontal } from 'lucide-svelte';

  export let currentPage: number = 1;
  export let totalPages: number = 1;
  export let onPageChange: (page: number) => void = () => {};
  export let maxVisiblePages: number = 5;

  // Calculate visible page numbers with ellipsis
  $: pages = (() => {
    if (totalPages <= 1) return [];
    
    const range = (start: number, end: number) => 
      Array.from({ length: end - start + 1 }, (_, i) => start + i);
    
    if (totalPages <= maxVisiblePages) {
      return range(1, totalPages);
    }
    
    const half = Math.floor(maxVisiblePages / 2);
    let start = Math.max(1, currentPage - half);
    let end = start + maxVisiblePages - 1;
    
    if (end > totalPages) {
      end = totalPages;
      start = Math.max(1, end - maxVisiblePages + 1);
    }
    
    const pages = range(start, end);
    
    if (start > 1) {
      if (start > 2) {
        pages.unshift('...');
      }
      pages.unshift(1);
    }
    
    if (end < totalPages) {
      if (end < totalPages - 1) {
        pages.push('...');
      }
      pages.push(totalPages);
    }
    
    return pages;
  })();

  function handlePageClick(page: number | string) {
    if (typeof page === 'number' && page >= 1 && page <= totalPages && page !== currentPage) {
      onPageChange(page);
    }
  }

  function goToPrevious() {
    if (currentPage > 1) {
      onPageChange(currentPage - 1);
    }
  }

  function goToNext() {
    if (currentPage < totalPages) {
      onPageChange(currentPage + 1);
    }
  }
</script>

<div class="flex items-center justify-between px-2">
  <div class="flex-1 flex justify-between sm:hidden">
    <Button
      variant="outline"
      on:click={goToPrevious}
      disabled={currentPage === 1}
      class="px-4 py-2"
    >
      Previous
    </Button>
    <Button
      variant="outline"
      on:click={goToNext}
      disabled={currentPage === totalPages}
      class="px-4 py-2"
    >
      Next
    </Button>
  </div>
  
  <div class="hidden sm:flex sm:flex-1 sm:items-center sm:justify-between">
    <div>
      <p class="text-sm text-muted-foreground">
        Page <span class="font-medium">{currentPage}</span> of <span class="font-medium">{totalPages}</span>
      </p>
    </div>
    <div>
      <nav class="flex items-center space-x-1" aria-label="Pagination">
        <Button
          variant="ghost"
          size="icon"
          on:click={goToPrevious}
          disabled={currentPage === 1}
          aria-label="Previous page"
        >
          <ChevronLeft class="h-4 w-4" />
        </Button>
        
        {#each pages as page (page)}
          {#if page === '...'}
            <Button variant="ghost" size="icon" disabled class="cursor-default">
              <MoreHorizontal class="h-4 w-4" />
            </Button>
          {:else}
            <Button
              variant={page === currentPage ? 'default' : 'ghost'}
              size="icon"
              on:click={() => handlePageClick(page)}
              aria-current={page === currentPage ? 'page' : undefined}
              aria-label={`Go to page ${page}`}
            >
              {page}
            </Button>
          {/if}
        {/each}
        
        <Button
          variant="ghost"
          size="icon"
          on:click={goToNext}
          disabled={currentPage === totalPages}
          aria-label="Next page"
        >
          <ChevronRight class="h-4 w-4" />
        </Button>
      </nav>
    </div>
  </div>
</div>
