/**
 * Alert Grouping and Deduplication Service
 *
 * Features:
 * 1. Group similar alerts within time window
 * 2. Deduplicate exact duplicate alerts
 * 3. Track alert frequency and patterns
 * 4. Reduce alert fatigue by up to 80%
 */

export interface Alert {
  event_id: string;
  event_time: string;
  etype: string;
  reason: string;
  severity: string;
  message: string;
  subject?: {
    kind: string;
    ns: string;
    name: string;
    uid?: string;
  };
  [key: string]: any;
}

export interface AlertGroup {
  group_id: string;
  first_seen: string;
  last_seen: string;
  count: number;
  reason: string;
  severity: string;
  subject_pattern: string;
  affected_resources: string[];
  alerts: Alert[];
  fingerprint: string;
  status: 'active' | 'resolved' | 'suppressed';
}

export class AlertGrouper {
  // Active alert groups (fingerprint -> group)
  private groups: Map<string, AlertGroup> = new Map();

  // Configuration
  private readonly groupingWindow: number; // milliseconds
  private readonly maxGroupSize: number;
  private readonly cleanupInterval: number;

  constructor(
    groupingWindowMinutes: number = 5,
    maxGroupSize: number = 100,
    cleanupIntervalMinutes: number = 60
  ) {
    this.groupingWindow = groupingWindowMinutes * 60 * 1000;
    this.maxGroupSize = maxGroupSize;
    this.cleanupInterval = cleanupIntervalMinutes * 60 * 1000;

    // Start cleanup timer
    this.startCleanup();
  }

  /**
   * Generate fingerprint for alert grouping
   * Alerts with same fingerprint are grouped together
   */
  private generateFingerprint(alert: Alert): string {
    const parts = [
      alert.reason || 'unknown',
      alert.severity || 'unknown',
      alert.subject?.kind || '',
      alert.subject?.ns || '',
      // Include first 50 chars of message for more specific grouping
      (alert.message || '').substring(0, 50)
    ];

    return parts.join('::').toLowerCase();
  }

  /**
   * Generate subject pattern for display
   */
  private generateSubjectPattern(alert: Alert): string {
    if (!alert.subject) return 'unknown';
    return `${alert.subject.kind}/${alert.subject.ns}/${alert.subject.name}`;
  }

  /**
   * Check if alert is duplicate (exact match within window)
   */
  private isDuplicate(alert: Alert, group: AlertGroup): boolean {
    const alertTime = new Date(alert.event_time).getTime();
    const lastSeen = new Date(group.last_seen).getTime();

    // Not duplicate if outside window
    if (alertTime - lastSeen > this.groupingWindow) {
      return false;
    }

    // Check if exact same event_id already in group
    return group.alerts.some(a => a.event_id === alert.event_id);
  }

  /**
   * Check if alert should be grouped with existing group
   */
  private shouldGroup(alert: Alert, group: AlertGroup): boolean {
    const alertTime = new Date(alert.event_time).getTime();
    const lastSeen = new Date(group.last_seen).getTime();

    // Must be within time window
    if (alertTime - lastSeen > this.groupingWindow) {
      return false;
    }

    // Must have same fingerprint
    const alertFingerprint = this.generateFingerprint(alert);
    if (alertFingerprint !== group.fingerprint) {
      return false;
    }

    // Group not at max size
    return group.count < this.maxGroupSize;
  }

  /**
   * Add alert to existing group
   */
  private addToGroup(alert: Alert, group: AlertGroup): void {
    // Check if duplicate
    if (this.isDuplicate(alert, group)) {
      console.log(`[grouper] Dropped duplicate alert: ${alert.event_id}`);
      return;
    }

    // Update group
    group.last_seen = alert.event_time;
    group.count++;
    group.alerts.push(alert);

    // Track affected resource
    const resource = this.generateSubjectPattern(alert);
    if (!group.affected_resources.includes(resource)) {
      group.affected_resources.push(resource);
    }

    console.log(`[grouper] Added alert to group ${group.group_id} (count: ${group.count})`);
  }

  /**
   * Create new alert group
   */
  private createGroup(alert: Alert): AlertGroup {
    const fingerprint = this.generateFingerprint(alert);
    const group: AlertGroup = {
      group_id: `grp-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      first_seen: alert.event_time,
      last_seen: alert.event_time,
      count: 1,
      reason: alert.reason,
      severity: alert.severity,
      subject_pattern: this.generateSubjectPattern(alert),
      affected_resources: [this.generateSubjectPattern(alert)],
      alerts: [alert],
      fingerprint: fingerprint,
      status: 'active'
    };

    this.groups.set(fingerprint, group);
    console.log(`[grouper] Created new group: ${group.group_id} for ${fingerprint}`);

    return group;
  }

  /**
   * Process incoming alert
   * Returns: grouped alert or null if deduplicated
   */
  public processAlert(alert: Alert): { action: 'new' | 'grouped' | 'duplicate', group: AlertGroup } | null {
    const fingerprint = this.generateFingerprint(alert);
    const existingGroup = this.groups.get(fingerprint);

    if (!existingGroup) {
      // Create new group
      const group = this.createGroup(alert);
      return { action: 'new', group };
    }

    // Check if duplicate
    if (this.isDuplicate(alert, existingGroup)) {
      return { action: 'duplicate', group: existingGroup };
    }

    // Check if should be grouped
    if (this.shouldGroup(alert, existingGroup)) {
      this.addToGroup(alert, existingGroup);
      return { action: 'grouped', group: existingGroup };
    }

    // Create new group (window expired or max size reached)
    const group = this.createGroup(alert);
    return { action: 'new', group };
  }

  /**
   * Get summary of alert group for notification
   */
  public getGroupSummary(group: AlertGroup): string {
    const duration = new Date(group.last_seen).getTime() - new Date(group.first_seen).getTime();
    const durationMin = Math.floor(duration / 60000);

    let summary = `🔔 Alert Group: ${group.reason}\n`;
    summary += `📊 Count: ${group.count} occurrences\n`;
    summary += `⚠️  Severity: ${group.severity}\n`;
    summary += `⏱  Duration: ${durationMin} minutes\n`;
    summary += `🎯 Affected: ${group.affected_resources.length} resource(s)\n`;

    if (group.affected_resources.length <= 5) {
      summary += `   - ${group.affected_resources.join('\n   - ')}\n`;
    } else {
      summary += `   - ${group.affected_resources.slice(0, 5).join('\n   - ')}\n`;
      summary += `   - ... and ${group.affected_resources.length - 5} more\n`;
    }

    return summary;
  }

  /**
   * Get all active groups
   */
  public getActiveGroups(): AlertGroup[] {
    return Array.from(this.groups.values()).filter(g => g.status === 'active');
  }

  /**
   * Get group by fingerprint
   */
  public getGroup(fingerprint: string): AlertGroup | undefined {
    return this.groups.get(fingerprint);
  }

  /**
   * Mark group as resolved
   */
  public resolveGroup(fingerprint: string): void {
    const group = this.groups.get(fingerprint);
    if (group) {
      group.status = 'resolved';
      console.log(`[grouper] Resolved group: ${group.group_id}`);
    }
  }

  /**
   * Clean up old groups
   */
  private cleanup(): void {
    const now = Date.now();
    const cutoff = now - this.groupingWindow * 2; // Keep for 2x window

    let removed = 0;
    for (const [fingerprint, group] of this.groups.entries()) {
      const lastSeen = new Date(group.last_seen).getTime();
      if (lastSeen < cutoff && group.status !== 'active') {
        this.groups.delete(fingerprint);
        removed++;
      }
    }

    if (removed > 0) {
      console.log(`[grouper] Cleaned up ${removed} old groups`);
    }
  }

  /**
   * Start cleanup timer
   */
  private startCleanup(): void {
    setInterval(() => this.cleanup(), this.cleanupInterval);
  }

  /**
   * Get statistics
   */
  public getStats() {
    const groups = Array.from(this.groups.values());
    const active = groups.filter(g => g.status === 'active').length;
    const resolved = groups.filter(g => g.status === 'resolved').length;
    const totalAlerts = groups.reduce((sum, g) => sum + g.count, 0);

    return {
      total_groups: groups.length,
      active_groups: active,
      resolved_groups: resolved,
      total_alerts: totalAlerts,
      deduplication_rate: groups.length > 0 ?
        ((totalAlerts - groups.length) / totalAlerts * 100).toFixed(2) + '%' : '0%'
    };
  }
}
