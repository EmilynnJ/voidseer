<script>
  const testimonials = [
    {
      quote: 'I was skeptical at first, but my reading with Sarah was incredibly accurate and gave me the clarity I desperately needed. I feel so much lighter now.',
      author: 'Jessica M.',
      avatar: '/avatars/avatar-1.jpg'
    },
    {
      quote: 'The connection was instant and profound. David helped me understand my path forward. Truly a gifted reader and a compassionate soul.',
      author: 'Michael B.',
      avatar: '/avatars/avatar-2.jpg'
    },
    {
      quote: 'SoulSeer is my go-to platform for guidance. The readers are authentic, and the platform is so easy to use. Highly recommended!',
      author: 'Emily R.',
      avatar: '/avatars/avatar-3.jpg'
    }
  ];
</script>

<section class="py-16 md:py-24 bg-background">
  <div class="container mx-auto px-4">
    <div class="text-center mb-12">
      <h2 class="text-3xl md:text-4xl font-bold text-primary">What Our Clients Say</h2>
      <p class="mt-4 text-lg text-muted-foreground max-w-2xl mx-auto">
        Real stories from people who found clarity and guidance on SoulSeer.
      </p>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
      {#each testimonials as testimonial}
        <div class="bg-card p-6 rounded-lg shadow-sm flex flex-col">
          <p class="text-card-foreground flex-grow">"{testimonial.quote}"</p>
          <div class="flex items-center mt-6">
            <img src={testimonial.avatar} alt={testimonial.author} class="w-12 h-12 rounded-full mr-4" />
            <div>
              <p class="font-semibold text-card-foreground">{testimonial.author}</p>
            </div>
          </div>
        </div>
      {/each}
    </div>
  </div>
</section>
