import { motion } from 'motion/react';
import { useLocation } from 'react-router-dom';
import { TransitionType } from '../types';
import React from 'react';

interface PageTransitionProps {
  children: React.ReactNode;
}

export default function PageTransition({ children }: PageTransitionProps) {
  const location = useLocation();
  const transition = (location.state as any)?.transition as TransitionType || 'none';

  const variants = {
    push: {
      initial: { x: '100%' },
      animate: { x: 0 },
      exit: { x: '-100%' },
    },
    push_back: {
      initial: { x: '-100%' },
      animate: { x: 0 },
      exit: { x: '100%' },
    },
    slide_up: {
      initial: { y: '100%' },
      animate: { y: 0 },
      exit: { y: 0, opacity: 0 },
    },
    none: {
      initial: { opacity: 1 },
      animate: { opacity: 1 },
      exit: { opacity: 1 },
    },
  };

  const selectedVariant = variants[transition] || variants.none;

  return (
    <motion.div
      key={location.pathname}
      initial="initial"
      animate="animate"
      exit="exit"
      variants={selectedVariant}
      transition={{ duration: 0.3, ease: 'easeInOut' }}
      className="min-h-screen w-full touch-pan-y"
    >
      {children}
    </motion.div>
  );
}
