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
      initial: { x: '100%', opacity: 0.5 },
      animate: { x: 0, opacity: 1 },
      exit: { x: '-20%', opacity: 0.3, transition: { duration: 0.2 } },
    },
    push_back: {
      initial: { x: '-20%', opacity: 0.3 },
      animate: { x: 0, opacity: 1 },
      exit: { x: '100%', opacity: 0.5, transition: { duration: 0.2 } },
    },
    slide_up: {
      initial: { y: '100%', opacity: 0 },
      animate: { y: 0, opacity: 1 },
      exit: { y: '100%', opacity: 0, transition: { duration: 0.2 } },
    },
    none: {
      initial: { opacity: 0, scale: 0.98 },
      animate: { opacity: 1, scale: 1 },
      exit: { opacity: 0, scale: 0.98, transition: { duration: 0.15 } },
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
      transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
      className="min-h-screen w-full touch-pan-y"
    >
      {children}
    </motion.div>
  );
}
