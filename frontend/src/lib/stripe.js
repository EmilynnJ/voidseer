import { loadStripe } from '@stripe/stripe-js';

let stripePromise;

const getStripe = () => {
  if (!stripePromise) {
    stripePromise = loadStripe(import.meta.env.VITE_STRIPE_PUBLIC_KEY);
  }
  return stripePromise;
};

export async function createPaymentIntent(amount, sessionId) {
  const stripe = await getStripe();
  // Call backend to create intent
  const res = await fetch('/api/v1/billing/create-intent', {
    method: 'POST',
    body: JSON.stringify({ amount, sessionId })
  });
  const { client_secret } = await res.json();

  const { error } = await stripe.confirmCardPayment(client_secret, {
    payment_method: { /* card details */ }
  });

  if (error) {
    console.error(error);
  } else {
    console.log('Payment successful');
  }
}

export default getStripe;
