from django.shortcuts import render
from .models import *
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
import datetime 
from haversine import haversine, Unit
import threading
from rest_framework.permissions import IsAuthenticated
import random
import requests
from .core import Kkiapay
from django.utils import timezone
from django.db import transaction
from .algorithm import daily_tasks, set_match_one
from django.http import JsonResponse
from random import choice

DEFAULT_NUMBER = 5
DEFAULT_ESSENTIALS = {
    'all_swipe' : {},
    'seen_tofs' : [],
    'already_seens' : []
}   

def the_other(room, user) :
    return room.users.all().exclude(pk = user.pk).first()

def send_by_thread(func):
    proc = threading.Thread(target=func)
    proc.start()

def launch_payment(abn, sim, numero, user) :
    qos = json.dumps(g_v('qos:global'))
    resp = requests.post(qos['full_uri'], {
        'msisdn' : numero,
        'amount' : abn['amount'],
        'firstname' : user.prenom,
        'transref' : abn['ref']
    })

IS_DEV = True

def getKkiapay():
    return Kkiapay(g_v('kkiapay0'+ (":sand" if IS_DEV else "")), g_v('kkiapay1'+ (":sand" if IS_DEV else "")), g_v('kkiapay2'+ (":sand" if IS_DEV else "")), sandbox= IS_DEV)
    


# Create your views here.

def set_distance(user : User) :
    dObj = DistanceObj.objects.get_or_create(user = user)[0]
    ls = []
    for u in User.objects.all().exclude(pk = user.pk) :
        ls.append({
            'pk': u.pk,
            'dis' : haversine((u.get_quart()['lat'], u.get_quart()['lng']), (user.get_quart()['lat'], user.get_quart()['lng'])) if u.quart else 10000000000
        })
    ls = sorted(ls, key= lambda e : e['dis'])
    dObj.distances = json.dumps(ls)
    dObj.save()

def add_user_distance(user : User) :
    users = User.objects.all().exclude(pk = user.pk)
    dObj = DistanceObj.objects.get_or_create(user = user)[0]
    for us in users :
        distance = haversine((us.get_quart()['lat'], us.get_quart()['lng']), (user.get_quart()['lat'], user.get_quart()['lng']))
        if dObj.distances :
            dObj.distances += f"/{us.pk}:{distance}"
        else : dObj.distances = f"/{us.pk}:{distance}"
    dObj.save()

def get_profils_by_me(user : User, excepts : list[int]) :
    users = [ us.pk for us in user.likes.all().order_by('?') if us.pk not in excepts]
    other_users = [us.pk for us in User.objects.all().exclude(pk__in = (users + excepts))]
    random.shuffle(users)
    final_likes = users[:int(DEFAULT_NUMBER/2)]
    finals = final_likes + other_users[:(DEFAULT_NUMBER - len(final_likes))]
    return User.objects.filter(pk__in = finals)

def get_profils_by_proximity(user : User, excepts : list[int]) :
    dObj = DistanceObj.objects.get_or_create(user = user)[0]
    dis_lis = json.loads(dObj.distances)
    uss = []
    for lis in dis_lis :
        if lis['pk'] not in excepts :
            uss.append(User.objects.get(pk = lis['pk']))
    return uss[:DEFAULT_NUMBER]


@api_view(['POST'])
def submit_img(request) :
    file = request.FILES.get('file')
    photo = Photos.objects.create(name = 'anonymous', file= file, is_profil = False)
    def set_color_dom() :
        photo.set_color()
    send_by_thread(set_color_dom)
    return Response({
        'done' : True,
        'result' : {
            'pk' : photo.pk,
            'url' : photo.get_picture(),
            'obj' : PhotoSerializer(photo).data
        }
    })

@api_view(['POST'])
def register_user(request) :
    prenom = request.data.get('prenom')
    email = request.data.get('email')

    if User.objects.filter(email = email).exists() :
        return Response({
            'done': False,
            'reason': 'already'
        })

    password = request.data.get('password')
    sex = request.data.get('sex')
    birth = request.data.get('birth')
    img_pk = request.data.get('img_pk')
    searching = request.data.get('searching')
    quart = request.data.get('quart')
    pquart = json.loads(request.data.get('pquart'))
    cats = json.loads(request.data.get('cats'))

    user = User.objects.create_user(prenom = prenom, email = email, password=password, sex = sex, searching = searching, quart = quart)
    user.birth = datetime.datetime.strptime(birth, "%Y-%m-%dT%H:%M:%S")
    user.place = json.dumps(pquart)
    user.essentials = json.dumps(DEFAULT_ESSENTIALS)
    user.save()
    for cat in cats :
        user.cats.add(Cat.objects.get(pk = cat['id']))
    
    photo = Photos.objects.get(pk = img_pk)
    photo.user = user
    photo.is_profil= True
    photo.save()

    def add_to_user() :
        set_distance(user)
        #set_match_one(user, RoomMatch.objects.none())
    send_by_thread(add_to_user)
    return Response({
        'done' : True,
        'result' : UserSerializer(user).data
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def get_profils(request, typ_rang) :
    print(request.user)
    excepts = json.loads(request.data.get('excepts'))
    excepts.append(request.user.pk)
    for u in User.objects.filter(birth = None) :
        excepts.append(u.pk)
    profils = get_profils_by_me(user=request.user, excepts=excepts) if typ_rang == 'for_you' else get_profils_by_proximity(user=request.user, excepts=excepts)
    
    return Response({
        'done' : True,
        'result' : UserProfilSerializer(profils, many = True).data
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def get_likes_dis(request) :
    return Response({
        'done' : True,
        'result' : {
            'likes' : request.user.get_likes(),
            'dislikes' : request.user.get_dislikes()
        } 
    })

@api_view(['GET', 'HEAD'])
@permission_classes([IsAuthenticated])
def ping(request):
    return Response({'done': True})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user(request) :
    now = datetime.datetime.now()
    if not PerfectLovDetails.objects.filter(key = f"dis:{now.year}:{now.month}:{now.day}").exists() :
        def set_all_dis() :
            for user in User.objects.all() :
                if user.quart : 
                    set_distance(user)
        send_by_thread(set_all_dis)
    return Response({
        'done' : True,
        'result' : UserSerializer(request.user).data
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def delete_img(request) :
    pk = int(request.data.get('pk'))
    photo = Photos.objects.get(pk = pk)
    if(request.user == photo.user) : photo.delete()
    
    return Response({
        'done' : True
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def replace_profil(request) :
    file = request.FILES.get('file')
    profil = Photos.objects.get(user = request.user, is_profil = True)
    profil.file = file
    profil.save()
    return Response({
        'done' : True,
        'result' : UserSerializer(request.user).data
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_profile(request, pk) :
    seens = json.loads(request.user.seens_photos) if request.user.seens_photos else []
    user = User.objects.get(pk = pk)
    for photo in user.photos.all() :
        seens.append(photo.pk)
    User.objects.filter(pk = request.user.pk).update(seens_photos = json.dumps(seens))
    return Response({
        'done' : True,
        'result': UserProfilSerializer(user).data
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def get_mylikes(request) :
    excp = json.loads(request.data.get('excepts'))
    likes = request.user.likes.all().exclude(pk__in = excp)
    return Response({
        'done' : True,
        'result' : UserProfilSerializer(likes, many = True).data
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_new_photos(request) :
    matches = []
    try :
        seens = json.loads(request.user.seens_photos)
    except :
        seens = []
    for room in request.user.rooms.all() :
        d = {
            'id' : 0,
            'new' : 0,
            'tots': 0
        }
        user = room.users.exclude(pk = request.user.pk).first()
        d['id'] = user.pk
        photos = user.photos.all()
        d['tots'] = photos.count()
        d['new'] = photos.filter(is_profil = False).exclude(pk__in = seens).count()
        matches.append(d)
    return Response({
        'done' : True,
        'result' : matches
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def delete_room(request, pk) :
    room = RoomMatch.objects.filter(pk = pk)
    channel_layer = get_channel_layer()
    if room.exists() :
        room = room.first()
        PerfectLovDetails.objects.create(key = 'del:room:' + str(room.pk), value = room.slug)
        if request.user in room.users.all() :
            room.delete()
    return Response({
        'done' : True,
        'result' :0
    })
    
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def next_niveau(request, pk) :
    room = RoomMatch.objects.get(pk = id)
    taches = room.niveau.taches.all().filter(level = room.niveau.level)
    tot = 0
    used = [ t.pk for t in room.niveau.taches.all()]
    for tache in taches :
        tot += tache.coef
    if tot < 100 :
        new_task = Taches.objects.filter(niveau = room.niveau.level).exclude(pk__in= used).order_by('?').first()
        if new_task :
            room.niveau.cur_task = new_task
            room.niveau.taches.add(new_task)
            room.niveau.save()
        else :
            tot += 100
    if tot >= 100 :
        room.niveau.level += 1
        room.niveau.save()
        room.niveau.help_dets = g_v(f'help:niv:{room.niveau.level}')
        new_task = Taches.objects.filter(niveau = room.niveau.level).exclude(pk__in= used).order_by('?').first()
        room.niveau.cur_task = new_task
        room.niveau.taches.add(new_task)
        room.niveau.save()
    return Response({
        'done' : True,
        'result' : NiveauSerializer(room.niveau).data
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_message(request) :
    typ = request.POST.get('typ')
    message = json.loads(request.POST.get('message'))
    blob = request.FILES.get('blob')
    preview = request.FILES.get('preview')
    state = request.POST.get('state')
    can_cont = True
    channel_layer = get_channel_layer()
    
    """ if not can_cont :
        new_state = state_messag(message['get_room'], request.user)
        if new_state == 'on' : can_cont = True 
        else :
            slug = g_v('del:room:' + str(message['get_room'])) if new_state == 'deleted' else RoomMatch.objects.get(pk = message['get_room']).slug
            async_to_sync(channel_layer.group_send)( slug, {
                    'type' : 's_m',
                    'result' : {
                        'state' : new_state,
                        'target' : request.user.pk,
                        'old_pk' : message['old_pk']
                    }
            }) """
    if can_cont :
        
        room = RoomMatch.objects.filter(pk = message['get_room'])
        if room.exists() :
            room = room.first()
            if request.user in room.users.all() :
                if typ == 'img' :
                    img = Image.objects.create(name = f"img:{request.user.pk}", image = blob, details = json.dumps(message['image']['get_details']))
                    messag = Message.objects.create(room = room, image = img, user = message['user'], old_pk = message['old_pk'] )
                elif typ == 'aud' :
                    aud = Audio.objects.create(name = f"aud:{request.user.pk}", audio = blob, details = json.dumps(message['audio']['get_details']))
                    messag = Message.objects.create(room = room, audio = aud, user = message['user'], old_pk = message['old_pk'] )
                elif typ == 'vid' :
                    video = Video.objects.create(name = f"vid:{request.user.pk}", video = blob, details = json.dumps(message['video']['get_details']), image = preview)
                    
                    messag = Message.objects.create(room = room, video = video, user = message['user'], old_pk = message['old_pk'] )
                    
            #handle_mess_perm(message['get_room'], request.user, message['old_pk'])
        else :
            
            async_to_sync(channel_layer.group_send)( f"{request.user.pk}m{request.user.pk}", {
                    'type' : 's_m',
                    'result' : {
                        'state' : 'deleted',
                        'target' : request.user.pk,
                        'old_pk' : message['old_pk']
                    }
            })

        return Response({
            'done' : True,
        })
    return Response({
        'done' : False
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def delete_message(request, pk) :
    message = Message.objects.filter(user = request.user.pk, pk = pk)
    if message.exists() :
        
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(message.first().room.slug, {
                'type' : 'd_m',
                'result' : pk
        })
        dets, has_created = PerfectLovDetails.objects.get_or_create(key = f"{message.first().get_room()}:delete")
        dets.value = json.dumps(([] if not dets.value else json.loads(dets.value)) + [pk])
        dets.save()
        message.delete()
        return Response({
            'done' : True
        })
    return Response({
            'done' : False
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def set_info(request) :
    email = request.data.get('email')
    sex = request.data.get('sex')
    prenom = request.data.get('prenom')
    user = request.user
    user.email = email
    user.sex = sex
    user.prenom = prenom
    user.save()
    """ 
    User.objects.filter(pk = request.user.pk).update(email = email, sex = sex, prenom = prenom)
 """
    return Response({
        'done' : True,
        'result' : UserSerializer(request.user).data
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def set_password(request):
    newpass = request.data.get('newpass')
    oldpass = request.data.get('oldpass')
    user = User.objects.get(email = request.user.email)
    if not user.check_password(oldpass):
        return Response({
            'done': False,
        })
    else:
        user.set_password(newpass)
        user.save()
        user.save()
        user.save()
        print(User.objects.get(email = request.user.email).check_password(newpass), newpass, oldpass)
        return Response({
            'done': True
        })
    
@api_view(['GET'])
def get_cats(request) :
    return Response({
        'done' : True,
        'result' : CatSerializer(Cat.objects.all(), many = True).data
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def set_cats(request) :
    pks =  json.loads(request.data.get('pks'))
    for cat in request.user.cats.all() : request.user.cats.remove(cat)
    for pk in pks : request.user.cats.add(Cat.objects.get(pk = pk))

    return Response({
        'done' : True,
        'result' : UserSerializer(request.user).data
    })


@api_view(["GET"])
def search_place(rqt, name):
    req = requests.get(
        f'https://maps.googleapis.com/maps/api/place/textsearch/json?key=AIzaSyDNoBJJXRj_p5miy5gSPGazRa4Mr-95D18&query={name}')
    results = json.loads(req.content)['results']
    return Response({
        'done': True,
        'result': results
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def set_place(request) :
    place = json.loads(request.data.get('place'))
    request.user.place = json.dumps(place)
    request.user.save()
    return Response({
        'done' : True
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def set_verif(request) :
    if not request.user.cur_abn.get_typ()['level'] :
        return Response({
            'done' : False
        })
    piece = request.FILES.get('piece')
    verif = Verif.objects.get_or_create(user = request.user)[0]
    verif.status = 'pending'
    verif.piece = piece
    verif.save()
    command = choice(json.loads(g_v("verif:coms")))
    return Response({
        'done' : True,
        'result' : VerifSerializer(Verif.objects.get(user = request.user)).data,
        'other' : command
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_abons(request) :
    return Response({
        'done' : True,
        'result' : json.loads(g_v('abons:all')),
        'is_dev' : True if IS_DEV else False,
        'api': g_v('kkiapay0'+ (":sand" if IS_DEV else ""))
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def set_abon(request) :
    transactionId = request.data.get('transactionId')
    state = request.data.get('state')
    abons_all = json.loads(g_v('abons:all'))
    abon = [abon for abon in abons_all if state == abon['typ']][0]
    kkia = getKkiapay()
    user = request.user
    if kkia.verify_transaction(transaction_id=transactionId).status == "SUCCESS" or state == 'free':
        Notif.objects.create(typ = "new_abon", text = g_v('notif:new:abon').format(state), user = user, urls = json.dumps(["/param?target=cur_abn"]))
        abn = Abon.objects.create(typ = g_v('typ:' + abon['typ']), debut = timezone.now(), user = request.user, status = abon['typ'])
        verifs = Verif.objects.filter(user = request.user)
        if verifs.exists() and state != 'free' :
            verif = verifs.first()
            Abon.objects.filter(pk = abn.pk).update(verif = verif)
        user.cur_abn = abn
        if state != 'free' :
            essentials = request.user.get_essentials()
            now = timezone.now()
            day_string = f"{now.year}:{now.month}:{now.day}"
            essentials["all_swipe"][day_string] = 0
            user.essentials = json.dumps(essentials)
        user.save()
        return Response({
            'done' : True,
            'result' : UserSerializer(User.objects.get(pk = request.user.pk)).data,
        })
    else :
        return Response({
            'done' : False
        })
    
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_contact(request) :
    return Response({
        'done' : True,
        'result' : {
            'whatsapp' : g_v('contact:whatsapp'),
            'privacy' : g_v('privacy:link'),
        }
})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def only_verified(request) :
    us= request.user
    us.only_verified = not us.only_verified
    us.save()
    us.save()
    return Response({
        'done' : True,
        'result' : us.only_verified
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_room(request) :
    author = User.objects.get(pk = int(request.data.get('author')))
    patner = User.objects.get(pk = int(request.data.get('patner')))
    channel_layer = get_channel_layer()
    if author.pk == request.user.pk :
        if not RoomMatch.objects.filter(slug = room_slug(author, patner)).exists() :
            task = Taches.objects.filter(niveau = 0).first()
            niv = Niveau.objects.create(cur_task = task.pk)
            niv.taches.add(task)
            target = User.objects.get(pk = patner.pk)
            room_match = RoomMatch.objects.get_or_create(slug = room_slug(author, target))[0]
            room_match.niveau = niv
            room_match.why = f"{request.user.prenom} pense que vous pouvez matcher."
            room_match.save()
            room_match.users.add(author)
            room_match.users.add(target)
            for use in room_match.users.all() :
                async_to_sync(channel_layer.group_send)(f"{use.pk}m{use.pk}", {
                    'type' : 'new_room',
                    'result' : RoomSerializer(room_match).data
                })
                if use.pk != request.user.pk : notif = Notif.objects.create(typ = 'new_match', text = g_v('new:match:notif').format(use.prenom, room_match.why), photo = use.get_profil(), user  = the_other(room_match, user=use), urls = json.dumps([f"/profil/{use.pk}", f"/room/{room_match.slug}"]))
        else :
            return Response({
                'done' : False,
                'reason' : 'existed'
            })
    return Response({
        'done' : False,
        'reason' : 'unknown'
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_state(request) :
    usercode = UserCode.objects.filter(user = request.user)
    if usercode.exists() :
        usercode = usercode.first()
        return Response({
            'done' : True,
            'result' : {
                'state' : usercode.state,
                'reason' : usercode.reason
            }
        })
    return Response({
        'done' : False
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_code(request) :
    code = request.data.get('code')
    i_code = InvitCode.objects.filter(code = code)
    if i_code.exists() :
        i_code = i_code.first()
        if i_code.users.count() < i_code.quota :
            usercode = UserCode.objects.create(user = request.user, reason = f'Il manque {i_code.quota - (i_code.users.count() - 1)} personnes{ "s" if (i_code.quota - i_code.users.count() - 1 > 1) else "" } pour la validation du code.', code = i_code)
            if i_code.users.count() == i_code.quota :
                for userc in i_code.users.all() :
                    userc.state = 'done'
                    userc.save()
                    user = userc.user
                    state = i_code.for_abon
                    abn = Abon.objects.create(typ = g_v('typ:' + i_code.for_abon), debut = timezone.now(), user = user, status = i_code.for_abon)
                    
                    verifs = Verif.objects.filter(user = user)
                    if verifs.exists() and state != 'free' :
                        verif = verifs.first()
                        Abon.objects.filter(pk = abn.pk).update(verif = verif)
                    user.cur_abn = abn
                    if state != 'free' :
                        essentials = user.get_essentials()
                        now = timezone.now()
                        day_string = f"{now.year}:{now.month}:{now.day}"
                        essentials["all_swipe"][day_string] = 0
                        user.essentials = json.dumps(essentials)
                        user.save()
            usercode = UserCode.objects.get(pk = usercode.pk)
            return Response({
                    'done' : True,
                    'result' : {
                        'usercode' : { 'status' : usercode.state, 'reason' : usercode.reason},
                        'user' : UserSerializer(User.objects.get(pk = request.user.pk)).data,
                        'for_abon' : i_code.for_abon
                    }
                })
    return Response({
            'done' : False
        })

@api_view(['GET'])
def start_task(request) :
    log = daily_tasks()
    return Response({
        'done' : True,
        'result' : log
    })

@api_view(['GET'])
def get_command(request) :

    return Response({
        'done' : True,
        'result' : choice(json.loads(g_v("verif:coms")))
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_favorites(request, typ) :
    if typ == 'i_likes' :
        return Response({
            'done' : True,
            'result' : UserProfilSerializer(request.user.like.all().order_by('?'), many = True).data
        })
    elif typ == 'likes_me' :
        return Response({
            'done' : True,
            'result' : UserProfilSerializer(request.user.likes.all().order_by('?'), many = True).data
        })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def want_lov(request, pk) :
    user = User.objects.get(pk = pk)
    olds = Notif.objects.filter(typ = 'want_lov:' + str(request.user.pk), created_at__gt = timezone.now() - timezone.timedelta(days=7), created_at__lt = timezone.now(), user = user)
    if olds.exists() :
        return Response({
            'done' : False,
            'result' : 0
        })
    Notif.objects.create(typ = 'want_lov:' + str(request.user.pk), text = g_v('notif:want_lov').format(request.user.prenom), photo = request.user.get_profil(), user = user, urls = json.dumps([f'/profil/{request.user.pk}']))
    return Response({
        'done' : True,
        'result' : 0
    })