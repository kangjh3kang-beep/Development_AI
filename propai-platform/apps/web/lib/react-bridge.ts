"use client";

import React from 'react';

/**
 * React 19 shim for React 18-era libraries (like react-konva / react-reconciler).
 * React 19 moved internal fields from __SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED
 * to __CLIENT_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED (on client) or
 * __SERVER_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED (on server).
 */
if (typeof window !== 'undefined' && React.version.startsWith('19')) {
  const anyReact = React as any;
  if (!anyReact.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED) {
    anyReact.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED = 
      anyReact.__CLIENT_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED;
  }
}
