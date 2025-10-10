/**
 * Test suite for alert grouping functionality
 * Run: npx ts-node test-grouping.ts
 */

import { AlertGrouper, Alert } from './src/alert-grouper';

// Mock alerts for testing
function createMockAlert(
  reason: string,
  severity: string,
  podName: string,
  namespace: string,
  eventTime: Date
): Alert {
  return {
    event_id: `event-${Date.now()}-${Math.random()}`,
    event_time: eventTime.toISOString(),
    etype: 'k8s.event',
    reason: reason,
    severity: severity,
    message: `Test alert: ${reason}`,
    subject: {
      kind: 'Pod',
      ns: namespace,
      name: podName
    }
  };
}

function runTests() {
  console.log('🧪 Running Alert Grouping Tests\n');

  // Test 1: Basic grouping
  console.log('Test 1: Basic alert grouping');
  const grouper1 = new AlertGrouper(5, 100, 60);

  const alert1 = createMockAlert('CrashLoopBackOff', 'ERROR', 'app-pod-1', 'default', new Date());
  const alert2 = createMockAlert('CrashLoopBackOff', 'ERROR', 'app-pod-2', 'default', new Date());
  const alert3 = createMockAlert('CrashLoopBackOff', 'ERROR', 'app-pod-3', 'default', new Date());

  const result1 = grouper1.processAlert(alert1);
  console.log(`  Alert 1: ${result1?.action} (group: ${result1?.group.group_id})`);

  const result2 = grouper1.processAlert(alert2);
  console.log(`  Alert 2: ${result2?.action} (group: ${result2?.group.group_id})`);

  const result3 = grouper1.processAlert(alert3);
  console.log(`  Alert 3: ${result3?.action} (group: ${result3?.group.group_id})`);

  console.log(`  ✅ Expected: All 3 alerts in same group`);
  console.log(`  ${result1?.group.group_id === result2?.group.group_id && result2?.group.group_id === result3?.group.group_id ? '✅ PASS' : '❌ FAIL'}\n`);

  // Test 2: Deduplication
  console.log('Test 2: Duplicate detection');
  const grouper2 = new AlertGrouper(5, 100, 60);

  const alert4 = createMockAlert('OOMKilled', 'ERROR', 'app-pod-1', 'default', new Date());
  const alert4Dup = { ...alert4 }; // Exact duplicate

  const result4 = grouper2.processAlert(alert4);
  console.log(`  Alert 4: ${result4?.action}`);

  const result4Dup = grouper2.processAlert(alert4Dup);
  console.log(`  Alert 4 (duplicate): ${result4Dup?.action}`);

  console.log(`  ✅ Expected: Duplicate detected`);
  console.log(`  ${result4Dup?.action === 'duplicate' ? '✅ PASS' : '❌ FAIL'}\n`);

  // Test 3: Different alert types
  console.log('Test 3: Different alert types (should NOT group)');
  const grouper3 = new AlertGrouper(5, 100, 60);

  const alert5 = createMockAlert('OOMKilled', 'ERROR', 'app-pod-1', 'default', new Date());
  const alert6 = createMockAlert('ImagePullBackOff', 'ERROR', 'app-pod-1', 'default', new Date());

  const result5 = grouper3.processAlert(alert5);
  const result6 = grouper3.processAlert(alert6);

  console.log(`  Alert 5: ${result5?.action} (group: ${result5?.group.group_id})`);
  console.log(`  Alert 6: ${result6?.action} (group: ${result6?.group.group_id})`);

  console.log(`  ✅ Expected: Different groups`);
  console.log(`  ${result5?.group.group_id !== result6?.group.group_id ? '✅ PASS' : '❌ FAIL'}\n`);

  // Test 4: Time window expiration
  console.log('Test 4: Time window expiration');
  const grouper4 = new AlertGrouper(5, 100, 60); // 5-minute window

  const now = new Date();
  const sixMinutesAgo = new Date(now.getTime() - 6 * 60 * 1000);

  const alert7 = createMockAlert('CrashLoopBackOff', 'ERROR', 'app-pod-1', 'default', sixMinutesAgo);
  const alert8 = createMockAlert('CrashLoopBackOff', 'ERROR', 'app-pod-1', 'default', now);

  const result7 = grouper4.processAlert(alert7);
  const result8 = grouper4.processAlert(alert8);

  console.log(`  Alert 7 (6 min ago): ${result7?.action} (group: ${result7?.group.group_id})`);
  console.log(`  Alert 8 (now): ${result8?.action} (group: ${result8?.group.group_id})`);

  console.log(`  ✅ Expected: Different groups (window expired)`);
  console.log(`  ${result7?.group.group_id !== result8?.group.group_id ? '✅ PASS' : '❌ FAIL'}\n`);

  // Test 5: Group summary
  console.log('Test 5: Group summary generation');
  const grouper5 = new AlertGrouper(5, 100, 60);

  const alert9 = createMockAlert('OOMKilled', 'ERROR', 'app-pod-1', 'default', new Date());
  const alert10 = createMockAlert('OOMKilled', 'ERROR', 'app-pod-2', 'default', new Date());
  const alert11 = createMockAlert('OOMKilled', 'ERROR', 'app-pod-3', 'default', new Date());

  grouper5.processAlert(alert9);
  grouper5.processAlert(alert10);
  const result11 = grouper5.processAlert(alert11);

  if (result11) {
    const summary = grouper5.getGroupSummary(result11.group);
    console.log('  Group summary:');
    console.log(summary.split('\n').map(line => `    ${line}`).join('\n'));
    console.log(`  ✅ Expected: Summary shows 3 occurrences, 3 affected resources`);
    console.log(`  ${result11.group.count === 3 && result11.group.affected_resources.length === 3 ? '✅ PASS' : '❌ FAIL'}\n`);
  }

  // Test 6: Statistics
  console.log('Test 6: Grouper statistics');
  const stats = grouper5.getStats();
  console.log(`  Total groups: ${stats.total_groups}`);
  console.log(`  Active groups: ${stats.active_groups}`);
  console.log(`  Total alerts: ${stats.total_alerts}`);
  console.log(`  Deduplication rate: ${stats.deduplication_rate}`);
  console.log(`  ✅ Expected: Deduplication rate > 0%`);
  console.log(`  ${parseFloat(stats.deduplication_rate) > 0 ? '✅ PASS' : '❌ FAIL'}\n`);

  // Test 7: Severity grouping
  console.log('Test 7: Different severities (should NOT group)');
  const grouper6 = new AlertGrouper(5, 100, 60);

  const alert12 = createMockAlert('OOMKilled', 'WARNING', 'app-pod-1', 'default', new Date());
  const alert13 = createMockAlert('OOMKilled', 'ERROR', 'app-pod-1', 'default', new Date());

  const result12 = grouper6.processAlert(alert12);
  const result13 = grouper6.processAlert(alert13);

  console.log(`  Alert 12 (WARNING): ${result12?.action} (group: ${result12?.group.group_id})`);
  console.log(`  Alert 13 (ERROR): ${result13?.action} (group: ${result13?.group.group_id})`);

  console.log(`  ✅ Expected: Different groups (different severity)`);
  console.log(`  ${result12?.group.group_id !== result13?.group.group_id ? '✅ PASS' : '❌ FAIL'}\n`);

  // Summary
  console.log('=' .repeat(60));
  console.log('Test suite completed!');
  console.log('=' .repeat(60));
}

// Run tests
runTests();
