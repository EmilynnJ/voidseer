# SoulSeer Frontend

This is the frontend for the SoulSeer application, built with SvelteKit and Tailwind CSS.

## Prerequisites

- Node.js 18+ (LTS recommended)
- npm (comes with Node.js) or yarn

## Getting Started

1. **Install Dependencies**
   ```bash
   npm install
   # or
   yarn
   ```

2. **Environment Variables**
   Copy the example environment file and update the values as needed:
   ```bash
   cp .env.example .env
   ```

3. **Development Server**
   Start the development server:
   ```bash
   npm run dev
   # or
   yarn dev
   ```
   The app will be available at http://localhost:5173

4. **Building for Production**
   ```bash
   npm run build
   # or
   yarn build
   ```

## Project Structure

- `src/` - Source files
  - `app.html` - Main HTML template
  - `app.d.ts` - TypeScript type declarations
  - `lib/` - Shared components and utilities
    - `components/` - Reusable UI components
    - `api/` - API client and services
  - `routes/` - Application routes and pages
  - `app.css` - Global styles

## Technologies Used

- [SvelteKit](https://kit.svelte.dev/) - Web framework
- [TypeScript](https://www.typescriptlang.org/) - Type checking
- [Tailwind CSS](https://tailwindcss.com/) - Utility-first CSS framework
- [Tailwind Variants](https://www.tailwind-variants.org/) - Type-safe component variants
- [Lucide Icons](https://lucide.dev/) - Icon library

## Development

- **Linting**: `npm run lint`
- **Type Checking**: `npm run check`
- **Formatting**: `npm run format`

## Deployment

This project is configured to be deployed to Vercel, Netlify, or any other static hosting service.

## License

Proprietary - All rights reserved.
