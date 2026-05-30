/**
 * Launcher entry point.
 *
 * Boots the router, instantiates the shared touch client and health
 * pill, and registers the four views. Views are stubs for the scaffold
 * commit; the next commit fills them in.
 */

import { HealthPill } from './health-pill.js';
import { Router } from './router.js';
import { TouchClient } from './ws-client.js';
import { renderCalibrate } from './views/calibrate.js';
import { renderGames } from './views/games.js';
import { renderStatus } from './views/status.js';
import { renderTest } from './views/test.js';

const touch = new TouchClient();
touch.start();

const pill = new HealthPill(document.getElementById('health-pill'));
pill.start();

const router = new Router(document.getElementById('view-root'));
router
  .add('calibrate', renderCalibrate)
  .add('test', renderTest)
  .add('games', renderGames)
  .add('status', renderStatus);
router.start({ touch });

window.addEventListener('beforeunload', () => {
  touch.stop();
  pill.stop();
  router.stop();
});
