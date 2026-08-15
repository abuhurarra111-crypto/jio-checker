from flask import Flask, render_template, request, session, jsonify, redirect, url_for
import requests
import os
import uuid

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24).hex())

# Temporary storage for API sessions
temp_store = {}

def get_clean_number(number):
    clean = "".join(filter(str.isdigit, number))
    if len(clean) > 10 and clean.startswith("91"):
        clean = clean[-10:]
    return clean

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/check', methods=['POST'])
def api_check():
    """Step 1: Check if number is valid Jio number"""
    phone = request.form.get('phone', '').strip()
    clean = get_clean_number(phone)

    if len(clean) != 10:
        return jsonify({'ok': False, 'error': '❌ Please enter a valid 10-digit Indian mobile number'})

    try:
        url = f"https://www.jio.com/api/jio-recharge-service/recharge/mobility/number/{clean}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://www.jio.com/"
        }
        res = requests.get(url, headers=headers, timeout=10)

        if res.status_code == 200:
            data = res.json()
            primary = data.get('primaryService', {})
            session['phone'] = clean
            return jsonify({
                'ok': True,
                'phone': clean,
                'billing': primary.get('billingType', 'N/A'),
                'prime': primary.get('primeMember', False)
            })
        else:
            return jsonify({'ok': False, 'error': '❌ This number is NOT a registered Jio number'})

    except Exception as e:
        return jsonify({'ok': False, 'error': f'❌ Error: {str(e)}'})

@app.route('/api/send-otp', methods=['POST'])
def api_send_otp():
    """Step 2: Send OTP to the verified Jio number"""
    if 'phone' not in session:
        return jsonify({'ok': False, 'error': '❌ Session expired. Please refresh and try again.'})

    phone = session['phone']
    api_session = requests.Session()
    api_session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://www.jio.com",
        "Referer": "https://www.jio.com/selfcare/login/",
    })

    try:
        otp_url = "https://www.jio.com/api/jio-login-service/login/sendOtp"
        payload = {"mobileNumber": phone, "loginFlowType": "MOBILE", "alternateNumber": ""}
        res = api_session.post(otp_url, json=payload, timeout=10)

        if res.status_code == 200:
            sid = str(uuid.uuid4())
            temp_store[sid] = {'session': api_session, 'phone': phone}
            session['api_sid'] = sid
            return jsonify({'ok': True, 'message': '✅ OTP sent successfully to your phone!'})
        else:
            return jsonify({'ok': False, 'error': f'❌ Failed to send OTP. Status: {res.status_code}'})

    except Exception as e:
        return jsonify({'ok': False, 'error': f'❌ Error sending OTP: {str(e)}'})

@app.route('/api/verify-otp', methods=['POST'])
def api_verify_otp():
    """Step 3: Verify OTP"""
    if 'phone' not in session or 'api_sid' not in session:
        return jsonify({'ok': False, 'error': '❌ Session expired. Please refresh and try again.'})

    otp = request.form.get('otp', '').strip()
    if not otp:
        return jsonify({'ok': False, 'error': '❌ Please enter the OTP'})

    sid = session['api_sid']
    if sid not in temp_store:
        return jsonify({'ok': False, 'error': '❌ Session expired. Please refresh and try again.'})

    api_session = temp_store[sid]['session']

    try:
        validate_url = "https://www.jio.com/api/jio-login-service/login/validateOtp"
        payload = {"otp": otp}
        res = api_session.post(validate_url, json=payload, timeout=10)

        if res.status_code == 200:
            session['logged_in'] = True
            return jsonify({'ok': True, 'message': '✅ OTP verified! Now fetching plans...'})
        else:
            try:
                err = res.json().get('errorMessage', 'Invalid OTP')
            except:
                err = 'OTP verification failed'
            return jsonify({'ok': False, 'error': f'❌ {err}'})

    except Exception as e:
        return jsonify({'ok': False, 'error': f'❌ Error: {str(e)}'})

@app.route('/api/fetch-plans', methods=['POST'])
def api_fetch_plans():
    """Step 4: Fetch recharge plans"""
    if 'phone' not in session or 'api_sid' not in session:
        return jsonify({'ok': False, 'error': '❌ Session expired. Please refresh and try again.'})

    sid = session['api_sid']
    if sid not in temp_store:
        return jsonify({'ok': False, 'error': '❌ Session expired. Please refresh and try again.'})

    api_session = temp_store[sid]['session']
    phone = temp_store[sid]['phone']

    results = []
    urls = ["https://tiny.jio.com/loginrecharge", "https://tiny.jio.com/loginirecharge"]

    for url in urls:
        try:
            res = api_session.get(url, timeout=15)
            content = res.text[:8000] if res.status_code == 200 else f"Failed (Status: {res.status_code})"
            results.append({'url': url, 'status': res.status_code, 'content': content})
        except Exception as e:
            results.append({'url': url, 'status': 'Error', 'content': str(e)})

    return jsonify({'ok': True, 'results': results, 'phone': phone})

@app.route('/api/reset', methods=['POST'])
def api_reset():
    session.clear()
    return jsonify({'ok': True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
