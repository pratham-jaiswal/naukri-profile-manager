import * as core from '@actions/core';
import * as fs from 'fs';
import { login } from './api/login';
import { uploadResume } from './api/uploadResume';
import { updateResumeHeadline } from './api/updateResumeHeadline';
import type { LoginCookies } from './utils/types';

export async function run(): Promise<void> {
  try {
    const username = core.getInput('username');
    const password = core.getInput('password');
    const profileId = core.getInput('profile_id');
    const mode = (core.getInput('mode') || 'both').toLowerCase();
    const headline = core.getInput('resume_headline').trim();
    const resumePathInput = core.getInput('resume_path');

    if (!['headline', 'resume', 'both'].includes(mode)) {
      throw new Error('MODE must be headline, resume, or both');
    }

    if (!username || !password || !profileId) {
      throw new Error('Username, password, and profile ID are required');
    }

    core.setSecret(username);
    core.setSecret(password);
    core.setSecret(profileId);

    if ((mode === 'headline' || mode === 'both') && !headline) {
      throw new Error('RESUME_HEADLINE is required for this mode');
    }

    if (headline.length > 250) {
      throw new Error('Resume headline cannot exceed 250 characters');
    }

    let selectedResume = '';

    if (mode === 'resume' || mode === 'both') {
      const paths = resumePathInput
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter((line) => line && !line.startsWith('#'));

      const validPaths = paths.filter((path) => {
        if (fs.existsSync(path) && fs.statSync(path).isFile()) {
          return true;
        }

        core.warning(`Resume file not found: ${path}`);
        return false;
      });

      if (validPaths.length === 0) {
        throw new Error('No valid resume files were provided');
      }

      const day = new Date();
      const selection =
        (day.getDate() + day.getDay() * 5 + day.getMonth() * 31) %
        validPaths.length;

      selectedResume = validPaths[selection];
    }

    core.info(`Starting Naukri update in ${mode} mode`);

    const cookies: LoginCookies | null = await login(username, password);

    if (
      !cookies ||
      !cookies.unid ||
      !cookies.nkwap ||
      !cookies.nauk_at ||
      !cookies.nauk_rt ||
      !cookies.nauk_sid
    ) {
      throw new Error(
        'Login failed or required authentication cookies are missing'
      );
    }

    if (mode === 'headline' || mode === 'both') {
      core.info('Updating resume headline...');

      const success = await updateResumeHeadline(cookies, profileId, headline);

      if (!success) {
        throw new Error('Resume headline update failed');
      }

      core.info('Resume headline updated successfully');
    }

    if (mode === 'resume' || mode === 'both') {
      core.info(`Uploading resume: ${selectedResume}`);

      const success = await uploadResume(cookies, selectedResume, profileId);

      core.setOutput('upload_status', success ? 'success' : 'failure');
      core.setOutput('upload_time', new Date().toISOString());

      if (!success) {
        throw new Error('Resume upload failed');
      }

      core.info('Resume uploaded successfully');
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';

    core.setFailed(message);
  }
}
